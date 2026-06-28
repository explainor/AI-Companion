# Instruction — 多段输出 / 角色分类法 / 管家自学习

> 自包含、可执行。依据 `CONTEXT.md`（2026-06-28 快照）。完成后归档到 `docs/specs/`，按"必跑检查"验收并报告。下面字段/签名/配置为参照实现，须对齐仓库真实命名，冲突处以现有代码为准。未写明处用工程常识，**不要**打破下列既有约束。

## 必须遵守的既有约束（来自 CONTEXT.md，逐条不得违反）
- 作用域由 `ScopeProfile` 决定，装配逻辑里**禁止**写 `if persona.owner_user_id` 这类硬分支。
- 反幻觉只靠**作用域隔离 + 白板声明 + 事实边界**，**禁止禁词黑名单**。
- 记忆/规则写入**只能发生在 AI 回复落库并记录时间戳之后**。
- 最近对话强署名格式：`显示名(真人|AI, id=N): 内容`。
- 配置项一律走 config 层，**禁止写死**在业务代码或数据行里。
- prompt 拼装唯一入口是 `backend/chat/context_assembler.py`。

## 本轮锁定的判断（Codex 不要再就这些发明策略）
1. 管家效忠其 owner。群聊中它对所有人友好可帮忙，但**绝不暴露 owner 私有作用域内容**，也**不接受其他成员盖过 owner 的指令**。
2. **"管家自训练" = 结构化记忆的自更新读写循环，不是模型微调。** 严禁任何 finetune / 权重训练路径。
3. 群聊（hybrid 作用域）中，owner 私有事实**默认不披露**（default-deny），仅当存在显式 allow 规则、或 owner 在该频道当面要求时才可越界。
4. 多段输出在群聊里要克制；**一串突发算作一次插话**，不是每条气泡一次。

---

# 里程碑 M1 · 聊天式多段输出

**问题**：现在是"一问一答"——模型产出一整段、后端机械切分，读起来仍是一坨被剁开的答案，不是人发微信那样的多条独立 beat。

**改法（生成层，不是切分层）**：让角色生成**直接产出离散消息数组**，每条是一个真正独立的 beat；装配器把每条作为独立 SSE message 发出，中间夹 typing + 延迟。

- `backend/chat/agents.py` / `backend/presence/policy.py`：角色/管家生成的返回类型从 `str` 改为 `list[str]`（消息段列表）。模型被提示**自行决定是否分段**：默认 1 段，只有自然时才 2-3 段（一个想法 / 一句追加 / 一个反应）。不要把一段话按句号切——要模型本就生成分开的几段。
- **按作用域配额**（写进 config，禁止硬编码）：
  ```python
  PRESENCE_DEFAULTS 增补:
    "presence.max_segments_group": 2,   # 群聊（催化剂场景）克制
    "presence.max_segments_dm": 4,      # 与自有 AI 私聊可话痨
  ```
  装配器按 `channel` 作用域取对应上限，超出则截断。
- **突发 = 一次插话**：`interjection_decisions` 仍按**每次派发一条**（现状如此，别改成每段一条）。`metrics/service.py` 计算 `ai_interjection_rate` / `ai_silence_rate` 时，一串多段视为**一次** `spoke=true`，不得按气泡数膨胀。
- 复用现有 `messages.chunk_group`：同一串突发的所有段落共享一个 `chunk_group`，便于前端聚合与统计回溯。typing 延迟复用现有 `sim_config` 机制。
- 每段仍是独立 message 行：`author_type="ai"`、`persona_id` 正确、强署名格式不变。

**验收**：
- [ ] 一次 AI 回合能产出 2-3 条**读起来彼此独立**的气泡（非切碎的段落）。
- [ ] 群聊封顶 2 段，私聊可到 4 段，由 config 控制、可调。
- [ ] 一串突发在 `interjection_decisions` 里是 1 行；`compare()` 的插话率不被多段污染。
- [ ] 同串突发共享 `chunk_group`；单段路径与强署名格式回归正常。

---

# 里程碑 M2 · 角色分类法（娱乐 / 自有 / 系统）

**目标**：把遗留的"公共 AI"概念清掉，落成三类角色，归属与编辑权限清晰，自有 AI 受限，管家可进群。

**模型变更（`backend/models.py`）**：
- `personas` 增 `kind`：枚举 `entertainment | owned | system`。
- `personas` 增 `creator_user_id`（作者/可编辑者；娱乐 AI 指向发布它的创作者或官方账号，自有 AI 指向 owner）。
- 迁移用现有 `migrate_sqlite()` 风格补列。

**作用域映射（经 `ScopeProfile`，不写硬分支）**：在 `backend/chat/scope.py` 的 ScopeProfile 解析里，按 `persona.kind` 决定作用域——
- `entertainment` → **public 作用域**：无任何消费用户的私有记忆、无 per-user relationship 私有态。对所有人一致。
- `owned` → **relationship / hybrid 作用域**（沿用现状）。
- `system`（管家）→ 现状 + owned 语义（见 M3）。
分类经 `kind` 流入 ScopeProfile，装配器**不得**新增 `if persona.owner_user_id` 之类分支。

**编辑权限（`backend/api/routes.py` 的 PATCH `/personas/{id}` 与 `/card`）**：
- `entertainment`：仅 `creator_user_id == X-User-Id` 可编辑。消费用户**不可编辑**。
- 消费用户想改娱乐 AI → 走**克隆**：新增 `POST /api/personas/{id}/clone`，复制成一个 `kind=owned`、`creator_user_id=当前用户` 的新角色（**占用自有名额**）。
- `owned`：仅 owner 可编辑。

**自有 AI 限额（config，禁硬编码）**：
```python
"personas.butler_auto_provision": True,   # 每个用户自动拥有 1 个管家
"personas.max_extra_owned": 1,            # 管家之外，用户最多再建/克隆 1 个自有 AI
```
创建/克隆端点强制校验上限，超限返回明确错误。

**管家进群**：管家是 `kind=system` 的 owned 角色，可像普通 persona 一样被 `POST /channels/{id}/members` 加入群聊。在群中解析为 **hybrid 作用域**（公共上下文自由 + 私有事实受 M3 披露门控）。群中行为遵守锁定判断 1（效忠 owner、不泄私有、不被他人指令盖过）——该行为通过 hybrid 作用域装配时注入的系统指令实现，不靠硬编码分支。

**种子迁移（`backend/seed.py`）**：把遗留"公共 AI"（如 `兄弟`/`老师`）重种为 `kind=entertainment`、`creator_user_id=官方/系统账号`、public 作用域。`管家` 保持 `kind=system`。

**验收**：
- [ ] 三类角色 `kind` 落库；娱乐 AI 对消费者只读、可克隆；克隆出的是 owned 且占名额。
- [ ] 自有 AI 受 `max_extra_owned` 限额，超限有明确报错。
- [ ] 管家能被加入群聊，解析为 hybrid 作用域；群中不暴露 owner 私有事实、不接受他人盖过 owner 的指令。
- [ ] 装配器未新增 `if persona.owner_user_id` 硬分支；分类全程经 `ScopeProfile`。
- [ ] `python -m compileall` 通过；`smoke_two_users.py` 通过。

---

# 里程碑 M3 · 管家自学习（核心资产：用户记忆 + 说话方式 + 学出来的披露边界）

**定位**：管家与用户高频交互，必须**从交互中学用户**——学他的说话方式、日常习惯，以及**什么能说什么不能说**。这是一个**结构化记忆的自更新读写循环**（见锁定判断 2：**不是 finetune**）。

**三类自维护资产，全部存管家私有作用域（`memory_facts`，scope=owner-private）**：
1. **风格画像** `predicate="style"`：用户语气、长度、用词、emoji、正式度。管家生成时**读它来贴合用户偏好**（把一段简洁的风格描述注入管家 system prompt，**不是**逐字模仿历史原文）。
2. **习惯/日常事实**：沿用现有 `memory_facts` + todo/memo/habit 账本，这是管家核心资产。
3. **披露规则** `predicate="disclosure_rule"`：对管家**自己的私有事实**的 allow/deny（例：`deny topic=健康`、`allow topic=工作`）。注意——这是对**自有私有事实**的作用域级 allow/deny，符合"作用域隔离"原则，**不是禁词黑名单**，不得做成内容关键词过滤。

**学习发生的时机（遵守既有约束）**：自更新**只在 AI 回复落库并打时间戳之后**运行，作为一次后台抽取，**复用管家现有的静默分析钩子**（`StewardService.run_for_user_message` 路径）。新增管家工具（接入现有 tool-loop / `ToolStore` 风格）：
- `update_style_profile(fields)`：增量更新风格画像。
- `add_disclosure_rule(rule)`：新增/更新一条披露规则。

**披露规则可被纠正（关键交互）**：当管家在群里要披露 / 刚披露了某私有事实，owner 纠正（发"别说那个" / 删除 / 编辑）→ 后台抽取据此**写入一条 deny 披露规则**。下次 hybrid 装配时即生效。这就是"学出来的墙"。

**披露门控的集成缝（唯一一处）**：在 `backend/chat/scope.py` / `context_assembler.py` 解析 **hybrid 作用域**、为 public 频道装配上下文时——在把任何 owner-private `memory_facts` 放进上下文**之前**，先过披露规则：
- 默认 **deny**（锁定判断 3）。
- 仅当命中显式 allow 规则、或 owner 在本频道当面要求，才放行该条私有事实。
此门控只此一处，不要散落到多个调用点。

**"利用核心资产训练自己"的落地含义**：管家用累积的风格画像 + 习惯，使 (a) 生成贴合用户风格、(b) 主动提醒更准、(c) 披露决策更稳。整个过程是 read → write → improve 的记忆循环，**无任何权重训练**。

**验收**：
- [ ] 管家在私聊后台抽取并更新 `style` / `disclosure_rule` / 习惯事实，且**均在回复落库且打时间戳之后**发生。
- [ ] 管家生成明显贴合用户风格（注入风格描述，非逐字搬运）。
- [ ] hybrid 群聊装配对 owner 私有事实**默认 deny**；命中 allow 或 owner 当面要求才放行。
- [ ] owner 一次"别说那个"式纠正后，对应私有事实在后续群聊中不再出现（生成了 deny 规则）。
- [ ] 披露门控只在 scope/装配的单一缝处实现；未引入禁词黑名单；未引入任何 finetune 路径。
- [ ] `compileall` + `smoke_two_users.py` 通过；若动前端再 `npm run build`。

---

## 构建顺序与回归
M1 → M2 → M3（M3 依赖 M2 的 owned/hybrid 与管家进群）。每个里程碑结束跑必跑检查，并确认既有验收不回退：SSE message/typing、管家 dock、双人 smoke、ai_enabled/metrics compare、强署名格式。

## 必跑检查
- `python -m compileall backend scripts`
- `python scripts/smoke_two_users.py`
- 改了前端才跑：`cd frontend && npm run build`

## 完成后报告
- 每个里程碑：改动文件清单、新增 config 键、新增/变更端点、验收勾选结果。
- 同步更新 `CONTEXT.md` 的代码快照（文件树 / 表结构 / 路由 / 完成状态），保证下次对话的 context 不漂移。
