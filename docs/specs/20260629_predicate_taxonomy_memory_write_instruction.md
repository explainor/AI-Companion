# Companion Agent — Predicate 词表 + 管家写入规则 + "关于我"页面

> 给 Codex 的自包含执行规格。未提及的内容不动；遇到模糊点用工程常识处理，不扩大范围，不破坏已有架构边界。

---

## 0. 本版定位

**依据**：CONTEXT.md（2026-06-29 快照）。

**本版做三件事：**

1. **Predicate 受控词表**：在代码层定义 `MEMORY_PREDICATES` 常量，所有 `memory_facts` 写入必须从词表选 predicate，不得自造。
2. **管家写入规则**：修订 `steward/service.py` 的静默分析提示词，注入词表 + 写入判断规则 + 冲突消解（supersedes）逻辑。明确 `memory_facts` 与 `todos`/`habits` 的职责边界。
3. **前端"关于我"页面完善**：现有 `GET /api/memory` 已返回 facts，前端已有记忆 tab。本版在此基础上按 predicate 前缀分组展示，每条显示人类可读标签，支持编辑 content 字段（predicate 不可改）。

**明确不动**：`memory_facts` 表结构（不加列）、`ScopeProfile`、`context_assembler.py`、`scope_summaries`、`todos`/`habits` 表结构、admin 界面、smoke 测试脚本。

---

## 1. 架构总原则

### 词表是常量，不是配置

`MEMORY_PREDICATES` 定义在 `backend/steward/predicates.py`（新建），是一个 Python dict，键为 predicate 字符串，值为元数据（中文标签、更新行为类型、所属分组）。

这是**代码常量，不走 settings 表**。原因：词表变更需要同步修改提示词和前端分组逻辑，不是运行时可热更的配置，走 settings 会制造假象。

### memory_facts vs todos/habits 的边界（硬约束）

| 信息类型 | 应写入 | 禁止写入 |
|---|---|---|
| "明天下午三点和叶子咖啡馆" | `todos`（有时间+地点+人物） | `memory_facts` |
| "用户每天看书 30 分钟" | `habits` | `memory_facts` |
| "用户喜欢深夜工作" | `memory_facts`（pref.schedule） | `todos` |
| "用户在备考全科医学" | `memory_facts`（goal.near） | `todos` |
| "叶子是用户最好的朋友" | `memory_facts`（relation.person） | `todos` |

判断原则：**有明确截止时间或可打卡的动作 → todos/habits；关于人的软性事实 → memory_facts。**

管家提示词中必须包含此边界说明，让模型在写入前先判断类型。

---

## 2. 数据模型变更

**不新增表，不新增列。** 现有 `memory_facts` 表的 `predicate`、`supersedes_id`、`confidence`、`created_at` 字段已完全满足需求。

唯一变化：`predicate` 字段值从自由文本收敛到受控词表——这是代码层约束，不是 schema 层约束。

---

## 3. 新增文件：`backend/steward/predicates.py`

```python
"""
受控 predicate 词表。
来源参照：Mem0 默认分类（personal_details / professional_details / user_preferences /
milestones / health / family）+ OpenAI ChatGPT 两层分法（saved memories / assistant
response preferences）。

update_behavior:
  "overwrite"  — 同 predicate 存在旧值时，写入新值并将旧值 supersedes_id 指向新 id。
  "state"      — 状态型，保留历史但不主动 supersede（用于进度类，旧值降权但不废弃）。
  "accumulate" — 累积型，永不 supersede，只新增。
"""

MEMORY_PREDICATES: dict[str, dict] = {
    # ── 第一层：稳定事实（overwrite）──────────────────────────────────────
    "profile.name": {
        "label": "称呼/名字",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "profile.location": {
        "label": "所在城市",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "profile.occupation": {
        "label": "职业/身份",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },
    "profile.life_stage": {
        "label": "当前人生阶段",
        "group": "基本信息",
        "update_behavior": "overwrite",
    },

    # ── 第二层：偏好与风格（overwrite）────────────────────────────────────
    "pref.communication": {
        "label": "沟通风格偏好",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.schedule": {
        "label": "作息规律",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.topic_like": {
        "label": "感兴趣的话题",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.topic_avoid": {
        "label": "不想聊的话题",
        "group": "偏好",
        "update_behavior": "overwrite",
    },
    "pref.response_style": {
        "label": "回复风格偏好",
        "group": "偏好",
        "update_behavior": "overwrite",
    },

    # ── 第三层：动态状态（state）──────────────────────────────────────────
    "project.current": {
        "label": "当前主要项目",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "project.progress": {
        "label": "项目最新进度",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "goal.near": {
        "label": "近期目标",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "goal.far": {
        "label": "长期方向",
        "group": "进行中的事",
        "update_behavior": "state",
    },
    "mood.current": {
        "label": "最近状态/情绪",
        "group": "最近状态",
        "update_behavior": "state",
    },

    # ── 第四层：关系与事件（accumulate）──────────────────────────────────
    "relation.person": {
        "label": "重要的人",
        "group": "关系",
        "update_behavior": "accumulate",
    },
    "relation.dynamic": {
        "label": "关系动态",
        "group": "关系",
        "update_behavior": "accumulate",
    },
    "event.recent": {
        "label": "近期重要事件",
        "group": "近期",
        "update_behavior": "accumulate",
    },
    "event.concern": {
        "label": "当前担忧/压力源",
        "group": "近期",
        "update_behavior": "accumulate",
    },
}

# 供提示词注入使用的紧凑格式
PREDICATE_PROMPT_BLOCK = "\n".join(
    f"- {k}（{v['label']}）[{v['update_behavior']}]"
    for k, v in MEMORY_PREDICATES.items()
)

# 分组顺序（前端展示用）
GROUP_ORDER = ["基本信息", "偏好", "进行中的事", "最近状态", "关系", "近期"]
```

---

## 4. 管家写入规则变更：`steward/service.py`

### 4.1 静默分析提示词修订

在 `run_for_user_message`（或等价的静默分析钩子）生成写入事实的那段提示词中，**替换原有的自由提取指令**，改为：

```
你是用户的私人管家，正在分析一段对话，决定是否写入长期记忆。

【职责边界 — 先判断类型再决定写哪里】
- 有明确时间/截止日期的行动项 → 写入 Todo（不写 memory_facts）
- 可以打卡的习惯（每天/每周做某事）→ 写入 Habit（不写 memory_facts）
- 关于用户本人的软性事实 → 写入 memory_facts（用下方词表）

【memory_facts 受控词表】
{PREDICATE_PROMPT_BLOCK}

如果没有匹配的 predicate，不写入。宁可漏掉，不要自造 predicate。

【写入规则】
1. overwrite 类：写入前查同 predicate 是否有现存事实。有则在新事实写入后，将旧事实的 supersedes_id 更新为新事实 id（标记为已过期）。
2. state 类：直接新增，不 supersede 旧值。
3. accumulate 类：直接新增。

【输出格式】（JSON 数组，无则返回空数组 []）
[
  {
    "predicate": "<词表中的 key>",
    "content": "<简洁的中文描述，不超过 50 字>",
    "confidence": 0.0~1.0
  }
]
```

注意：`{PREDICATE_PROMPT_BLOCK}` 在代码里用 `from backend.steward.predicates import PREDICATE_PROMPT_BLOCK` 导入后字符串替换。

### 4.2 supersedes 写入逻辑

在 `steward/service.py` 的 memory 写入路径中，新增函数 `resolve_supersedes`：

```python
def resolve_supersedes(
    session: Session,
    scope_type: str,
    scope_key: str,
    predicate: str,
    new_fact_id: int,
) -> None:
    """
    对 overwrite 类 predicate：将同 scope + 同 predicate 的旧事实
    supersedes_id 设为 new_fact_id，标记为已过期。
    仅在 MEMORY_PREDICATES[predicate]["update_behavior"] == "overwrite" 时调用。
    """
    from backend.steward.predicates import MEMORY_PREDICATES
    if MEMORY_PREDICATES.get(predicate, {}).get("update_behavior") != "overwrite":
        return
    old_facts = session.exec(
        select(MemoryFact).where(
            MemoryFact.scope_type == scope_type,
            MemoryFact.scope_key == scope_key,
            MemoryFact.predicate == predicate,
            MemoryFact.supersedes_id == None,  # noqa: E711
            MemoryFact.id != new_fact_id,
        )
    ).all()
    for f in old_facts:
        f.supersedes_id = new_fact_id
    session.commit()
```

在现有的 memory_facts 写入流程里，每写完一条 overwrite 类事实后调用此函数。

### 4.3 写入数量上限

每次静默分析最多写入 **3 条** memory_facts（防止单次对话写入过多噪音）。提示词中加一行：

```
每次最多输出 3 条，优先选置信度最高的。
```

### 4.4 全局事实上限（防 token 膨胀）

在 `context_assembler.py` 的 owner-private facts 注入路径中，查询时加 `ORDER BY created_at DESC LIMIT 60`，超出的旧事实不注入 prompt（但仍保留在数据库供用户查阅）。60 条 × 平均 30 token/条 ≈ 1800 token，可接受。

---

## 5. API 变更：`api/routes.py`

### 5.1 `GET /api/memory` 响应补充 predicate 元数据

现有接口已返回 `facts` 列表。在每条 fact 的响应 payload 中补充两个字段（从 `predicates.py` 读取，不改表结构）：

```json
{
  "id": 42,
  "predicate": "pref.schedule",
  "predicate_label": "作息规律",
  "predicate_group": "偏好",
  "content": "深夜效率最高",
  "confidence": 0.9,
  "created_at": "...",
  "superseded": false
}
```

`superseded` = `supersedes_id IS NOT NULL`，即已被新事实取代的旧值。

### 5.2 `GET /api/memory` 默认过滤已 superseded 事实

默认只返回 `supersedes_id IS NULL` 的事实（即当前有效值）。加一个可选 query param `?include_superseded=true` 供调试用，前端默认不传。

### 5.3 `GET /api/memory/predicates`（新增路由）

返回词表常量，供前端渲染分组标签用：

```python
@router.get("/api/memory/predicates")
def get_predicates():
    from backend.steward.predicates import MEMORY_PREDICATES, GROUP_ORDER
    return {"predicates": MEMORY_PREDICATES, "group_order": GROUP_ORDER}
```

---

## 6. 前端"关于我"页面完善（`App.jsx`）

现有记忆 tab 已有 facts 列表和 PATCH/DELETE。本版在此基础上：

### 6.1 分组展示

- 启动时调用 `GET /api/memory/predicates` 拿到 `GROUP_ORDER` 和各 predicate 的 label/group。
- facts 按 `predicate_group` 分组，按 `GROUP_ORDER` 顺序排列。
- 每个分组用折叠 section 展示（默认展开），分组标题显示中文名（"基本信息"/"偏好"等）。

### 6.2 每条 fact 的展示

```
[分组标题]
  ┌─────────────────────────────┐
  │ 🏷 作息规律                  │
  │ 深夜效率最高                 │  ← content，可点击编辑
  │ 置信度 0.9 · 6月29日         │  ← confidence + created_at
  │                    [编辑] [删除] │
  └─────────────────────────────┘
```

- 编辑只允许修改 `content` 字段，调用现有 `PATCH /api/memory/facts/{fact_id}`。
- predicate 标签只读，不允许用户改。
- 删除调用现有 `DELETE /api/memory/facts/{fact_id}`。

### 6.3 空状态

分组内没有事实时，显示一行浅色提示："管家会在对话中自动提炼，也可以手动添加"。

### 6.4 手动添加入口（可选，低优先级）

在每个分组右侧加一个 `+` 小按钮，点击后弹出一个极简输入框（只填 content），predicate 从下拉选（显示中文 label），调用 `POST /api/memory/facts`（若此路由不存在则新建，见下方）。

**此功能如实现复杂度超过 30 行，优先级降低，先 stub 成按钮不可用状态，后续迭代。**

### 6.5 新路由 `POST /api/memory/facts`（如手动添加功能实现）

```python
@router.post("/api/memory/facts")
def create_memory_fact(body: MemoryFactCreate, x_user_id: str = Header(...), session = Depends(get_session)):
    # 校验 predicate 在词表中
    # scope_type = "owner_private", scope_key = owner_private_scope_key(user_id, steward_id)
    # 写入并调用 resolve_supersedes（如为 overwrite 类）
```

---

## 7. 反屎山规约

- `backend/steward/predicates.py` 只包含常量定义，不 import 任何业务模块。其他模块 import 它，反向禁止。
- `resolve_supersedes` 是 supersede 逻辑的唯一实现点，不在其他地方散写同类判断。
- `context_assembler.py` 的 LIMIT 60 是唯一的 token 防膨胀点，不在多处设相同限制。
- 前端分组逻辑从 `GET /api/memory/predicates` 拿数据，不在前端硬编码分组名称。

---

## 8. 构建顺序

### M1：后端词表 + supersedes 逻辑（纯后端，无 UI 变化）

1. 新建 `backend/steward/predicates.py`，写入词表常量。
2. `steward/service.py`：替换静默分析提示词，实现 `resolve_supersedes`，写入时调用。
3. `context_assembler.py`：加 `LIMIT 60`。
4. 跑 `python -m compileall backend scripts` + `python scripts/smoke_two_users.py`。

### M2：API 补充

1. `GET /api/memory` 响应补充 `predicate_label`、`predicate_group`、`superseded` 字段。
2. 默认过滤 `supersedes_id IS NOT NULL` 的旧事实。
3. 新增 `GET /api/memory/predicates` 路由。
4. 跑检查。

### M3：前端分组展示

1. 实现分组 section + 每条 fact 的新布局。
2. 空状态文案。
3. 手动添加按钮（stub 或实现，视复杂度）。
4. 跑 `npm run build`。

---

## 9. 验收

### 词表约束
- [ ] `steward/predicates.py` 存在，包含全部 18 个 predicate，每个有 label/group/update_behavior。
- [ ] 静默分析后写入的 `memory_facts` 记录，predicate 字段值全部在词表内，无自造值。
- [ ] overwrite 类 predicate 写入新值后，同 scope 同 predicate 的旧值 `supersedes_id` 不为 NULL。
- [ ] state 类和 accumulate 类写入时不触发 supersede。
- [ ] 每次静默分析最多写入 3 条。

### API
- [ ] `GET /api/memory` 返回的每条 fact 包含 `predicate_label`、`predicate_group`、`superseded` 字段。
- [ ] 默认返回只含 `superseded=false` 的事实；`?include_superseded=true` 时含所有。
- [ ] `GET /api/memory/predicates` 返回词表和分组顺序。
- [ ] `context_assembler.py` 注入 prompt 的事实条数不超过 60 条。

### 前端
- [ ] 记忆 tab 按分组展示，顺序为：基本信息 → 偏好 → 进行中的事 → 最近状态 → 关系 → 近期。
- [ ] 每条 fact 显示中文 predicate 标签（不显示英文 key）、content、置信度、日期。
- [ ] 点击编辑只允许修改 content，predicate 标签不可修改。
- [ ] 空分组显示占位提示文案。

---

## 10. 需人类确认

### Codex 自行决定、无需确认

- 手动添加功能的 stub/实现判断（按 30 行复杂度标准自行决策）。
- `LIMIT 60` 的具体数值（可在 60±20 范围内根据实际测试调整）。
- 前端折叠 section 的默认展开/折叠状态（默认全展开）。

### 词表迭代（未来，不在本版）

当前 18 个 predicate 覆盖主要场景。以下情况可在后续版本扩展词表：
- 用户通过"关于我"页面发现某类信息无法被分类 → 新增 predicate。
- 某个 predicate 在实际使用中从未被提炼到 → 可考虑删除。

扩展词表时需同步：① `predicates.py` 常量 ② 管家提示词 ③ 无需改表结构或前端逻辑（前端从 API 动态读取）。
