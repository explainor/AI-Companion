# Companion Agent Context

这个文件是给 Claude 对话框使用的默认项目上下文入口。每次需要 Claude 做架构判断、诊断或产出 Instruction 时，优先粘贴本文件；如果信息不够，再补充 `项目架构总结.md` 或让 Codex 导出具体代码片段。

## 项目定位

一个多真人 + 多 AI 的群聊实验平台。真人和 AI 体在共享频道里对话，用于测量群聊轮替动力学。核心玩法包括用户把自己名下的私人 AI 带进共享群，也就是公共频道里的私人 AI 混合态。

## 技术栈

- 后端：FastAPI + SQLModel + SQLite + LiteLLM + SSE
- 前端：React + Vite
- 存储：根目录 `app.db`，不得提交
- 入口：`backend/main.py`
- 主要前端：`frontend/src/App.jsx`、`frontend/src/styles.css`

## 当前重要约束

- prompt 拼装集中在 `backend/chat/context_assembler.py`。
- 公共 / 私人 / 混合作用域由 `ScopeProfile` 决定，不在装配逻辑里写 `if persona.owner_user_id` 这类硬分支。
- 反幻觉只靠作用域隔离、白板声明、事实边界原则，禁止禁词黑名单。
- 记忆写入只能发生在 AI 回复落库并记录时间戳之后。
- 最近对话强署名格式：`显示名(真人|AI, id=N): 内容`。
- 配置项走 config 层，禁止写死在业务代码或数据行里。

## 协作流程

1. 用户把本文件和必要代码片段粘给 Claude 对话框。
2. Claude 对话框输出可执行的 `Instruction.md`。
3. 用户把 Instruction 文件拖进 Codex。
4. Codex 执行实现、归档 Instruction 到 `docs/specs/`、跑检查并报告验收。
5. 如果只剩前端视觉层，Codex 导出现有前端 context，用户发给 Claude Design。
6. Claude Design 只输出视觉、布局、交互层建议，再交给 Codex patch 和 build。

## 必跑检查

- 后端语法检查：`python -m compileall backend scripts`
- 双人 smoke 测试：`python scripts/smoke_two_users.py`
- 改了前端才跑：`cd frontend && npm run build`

## 详细架构

更完整的模块说明见 `项目架构总结.md`。

---


## 当前代码快照（Codex 最后更新：2026-06-28）

### 后端文件树

```text
backend/
├── __init__.py                         # 后端包标记。
├── agents.py                           # 兼容/历史 agent 入口文件，当前主要聊天 agent 在 backend/chat/agents.py。
├── main.py                             # FastAPI 应用入口，初始化数据库、种子数据、后台心跳、API 路由和静态前端挂载。
├── db.py                               # SQLite engine、session_scope、init_db 和幂等迁移 migrate_sqlite()；补齐 persona kind/creator_user_id 等列。
├── models.py                           # SQLModel 表模型：用户、频道、成员、消息、角色分类、结构化记忆、工具账本、指标等。
├── schemas.py                          # API 请求/响应 schema。
├── seed.py                             # 启动种子数据：官方用户、娱乐角色、系统管家、频道、角色卡和设置。
├── api/
│   ├── __init__.py                     # API 包标记。
│   └── routes.py                       # REST API 与 SSE 路由集中入口；角色权限、克隆、自有配额在此实现。
├── chat/
│   ├── __init__.py                     # chat 包标记。
│   ├── agents.py                       # 普通角色 LLM/tool-loop 调用；生成层返回消息段数组。
│   ├── archive_retrieval.py            # 历史消息检索触发、片段召回和检索 gate 日志。
│   ├── context_assembler.py            # prompt/上下文拼装唯一入口；hybrid 私有事实披露门控唯一集成点。
│   ├── media.py                        # 消息媒体文本化与图片 data URL 处理。
│   ├── membership.py                   # 频道成员、真人、AI 显示名与活跃成员查询；允许 system 管家进群。
│   ├── memory.py                       # MemoryStore 实现：SQLite 记忆与 Mem0/Chroma 兼容实现。
│   ├── relationship.py                 # PersonaState 熟悉度、最近语气、互动时间和里程碑更新。
│   ├── scope.py                        # ScopeProfile 解析，按 persona.kind 决定 public/relationship/hybrid 作用域。
│   └── service.py                      # ChatService 主业务：频道、消息、成员、AI 多段回复、SSE、管家触发。
├── core/
│   ├── __init__.py                     # core 包标记。
│   ├── config.py                       # 默认配置、settings 读取和模型解析；含多段/自有 AI 配额配置。
│   ├── interfaces.py                   # ToolStore、MemoryStore、ChatService、Transport 抽象接口。
│   ├── llm.py                          # LiteLLM 封装、provider_ready、tool loop、调用计数。
│   ├── time_context.py                 # 当前时间、频道间隔、角色间隔等时间上下文。
│   └── transport.py                    # SSETransport：push/push_nowait/subscribe。
├── metrics/
│   ├── __init__.py                     # metrics 包标记。
│   └── service.py                      # AI 在场/缺席、人↔人/人↔AI 换手和插话指标计算。
├── presence/
│   ├── __init__.py                     # presence 包标记。
│   ├── context.py                      # PresenceContext 数据结构。
│   ├── policy.py                       # InterjectionPolicy：是否插话与生成短回复；返回消息段列表。
│   └── triggers.py                     # presence 配置读取、基础概率/cooldown/cheap gate 判断。
├── steward/
│   ├── __init__.py                     # steward 包标记。
│   ├── agent.py                        # 管家 LLM/tool-loop 入口，含风格画像和披露规则工具。
│   └── service.py                      # 管家后台分析、dock 回复、主动提醒 tick、工具调用与 owner-private memory_facts 写入。
└── tools/
    ├── __init__.py                     # tools 包标记。
    └── sqlite_store.py                 # SQLiteToolStore：todo/memo/habit 工具账本实现。
```

### 前端文件树

```text
frontend/src/
├── App.jsx       # React 主入口与全部页面/面板组件。
└── styles.css    # 全局样式、三栏布局、聊天气泡、右侧面板、弹窗和响应式规则。
```

### 数据库表结构

| 表名 | 关键字段 | 用途 |
|---|---|---|
| `personas` | `id`, `name`, `system_prompt`, `model`, `is_system`, `kind`, `creator_user_id`, `model_role`, `model_override`, `sim_config` | AI/系统角色基础信息、角色分类与创作者归属。 |
| `persona_card` | `persona_id`, `owner_user_id`, `persona_core`, `self_identity`, `relationship_backstory`, `speaking_style`, `example_dialogues`, `world_info`, `voice`, `traits` | 结构化角色卡与私人 AI owner 信息。 |
| `persona_state` | `persona_id`, `familiarity`, `last_tone`, `last_interaction`, `last_interaction_at`, `milestones` | 角色关系状态与里程碑。 |
| `persona_notes` | `id`, `persona_id`, `content`, `updated_at` | 角色私有记忆/兼容缓存。 |
| `users` | `id`, `display_name`, `created_at` | 薄身份真人用户；种子含官方用户。 |
| `channels` | `id`, `type`, `title`, `created_at`, `is_system`, `pinned`, `archived`, `ai_enabled`, `created_by_user_id` | 私聊、群聊、管家系统频道。 |
| `channel_members` | `id`, `channel_id`, `member_type`, `member_id`, `persona_id`, `user_id`, `added_by_user_id`, `active`, `left_at` | 频道真人/AI 成员关系，支持 system 管家作为 agent 入群和软退出。 |
| `messages` | `id`, `channel_id`, `sender`, `persona_id`, `author_type`, `author_user_id`, `ai_enabled_snapshot`, `message_type`, `media_url`, `mime_type`, `file_name`, `content`, `created_at`, `status`, `chunk_group` | 聊天消息、附件消息、多段同组追踪和 AI 在场快照。 |
| `interjection_decisions` | `id`, `channel_id`, `created_at`, `considered`, `spoke`, `trigger_reason`, `suppressed_reason`, `latency_ms` | AI presence 插话决策日志；一次突发仍只写一行。 |
| `todos` | `id`, `title`, `status`, `due_time`, `priority`, `notes`, `repeat_rule`, `source`, `result`, `source_channel`, `created_at`, `completed_at` | 待办账本。 |
| `memos` | `id`, `content`, `created_at` | 备忘录账本。 |
| `habits` | `id`, `name`, `schedule`, `created_at` | 习惯定义。 |
| `habit_logs` | `id`, `habit_id`, `value`, `ts` | 习惯打卡记录。 |
| `settings` | `key`, `value` | 应用配置、模型、presence、多段上限、自有 AI 配额等。 |
| `scope_summaries` | `id`, `scope_type`, `scope_key`, `content`, `last_message_id`, `updated_at` | 按作用域滚动摘要。 |
| `memory_facts` | `id`, `scope_type`, `scope_key`, `subject_type`, `subject_id`, `predicate`, `content`, `source_message_id`, `confidence`, `supersedes_id`, `created_at` | 作用域隔离结构化长期事实；管家 owner-private 风格画像、习惯事实和披露规则写在这里。 |

### API 路由清单

```text
POST   /api/users
GET    /api/users
GET    /api/users/{user_id}
GET    /api/personas
POST   /api/personas
GET    /api/personas/{persona_id}
PATCH  /api/personas/{persona_id}
DELETE /api/personas/{persona_id}
POST   /api/personas/{persona_id}/clone
PATCH  /api/personas/{persona_id}/model
GET    /api/personas/{persona_id}/card
PATCH  /api/personas/{persona_id}/card
GET    /api/personas/{persona_id}/notes
GET    /api/persona-state
POST   /api/channels
GET    /api/channels
PATCH  /api/channels/{channel_id}
DELETE /api/channels/{channel_id}
DELETE /api/channels/{channel_id}/messages
GET    /api/channels/{channel_id}/messages
POST   /api/channels/{channel_id}/messages
GET    /api/channels/{channel_id}/members
POST   /api/channels/{channel_id}/members
DELETE /api/channels/{channel_id}/members/{member_type}/{member_id}
GET    /api/channels/{channel_id}/events              # SSE
POST   /api/channels/{channel_id}/attachments
POST   /api/channels/{channel_id}/ai_enabled
GET    /api/channels/{channel_id}/metrics
GET    /api/channels/{channel_id}/metrics/compare
GET    /api/todos
POST   /api/todos
PATCH  /api/todos/{todo_id}
DELETE /api/todos/{todo_id}
POST   /api/todos/reorder
GET    /api/memos
GET    /api/habits
GET    /api/habits/{habit_id}/stats
GET    /api/relations
GET    /api/schedule
GET    /api/steward/brief
GET    /api/steward/messages
POST   /api/steward/proactivity/tick
GET    /api/settings
PATCH  /api/settings
PUT    /api/settings/{key}
```

### 功能完成状态

- [x] SSE `message` / `typing` / `proactive` 事件推送。
- [x] 角色生成层返回消息段数组；保存时每段独立落库并推送，typing 延迟复用原机制。
- [x] 群聊多段上限 `presence.max_segments_group=2`，私聊上限 `presence.max_segments_dm=4`。
- [x] 同一串多段共享 `chunk_group`；单段路径不写 chunk_group。
- [x] Presence 一次突发仍只写一条 `interjection_decisions`，metrics compare 不按气泡数膨胀插话率。
- [x] persona 三分类落库：`entertainment` / `owned` / `system`，并记录 `creator_user_id`。
- [x] 娱乐 AI 仅 creator 可编辑；消费用户可通过 `POST /api/personas/{id}/clone` 克隆成 owned。
- [x] `owned` 创建/克隆受 `personas.max_extra_owned` 限额约束；系统管家不占额外 owned 名额。
- [x] 用户可自动获得 owner 管家；system 管家可作为 agent 加入群聊，owner 私有事实走 hybrid 门控。
- [x] `ScopeProfile` 按 persona.kind 决定 public/relationship/hybrid；装配器未新增 `if persona.owner_user_id` 硬分支。
- [x] 管家静默分析可写 `style`、`disclosure_rule`、memo/habit 类 owner-private `memory_facts`，发生在 AI 回复落库之后。
- [x] hybrid 群聊 owner-private facts 默认 deny；显式 allow 或 owner 当面要求才放行。
- [x] 管家风格画像会注入生成上下文，作为偏好描述使用，不逐字搬运历史原文。
- [x] 管家 dock 系统频道与前台管家对话。
- [x] Todo CRUD、完成、删除、reorder 接口占位兼容。
- [x] Memo/Habit 账本读取与 habit stats。
- [x] 频道创建、重命名、清空消息、删除非系统频道。
- [x] 频道成员添加/移除，支持真人和 AI 成员。
- [x] 双真人薄身份：`users` 表与 `X-User-Id`。
- [x] 群聊 AI 在场/缺席开关与 metrics compare。
- [x] Presence 插话门控：cooldown、概率、cheap model gate、插话决策日志。
- [x] 最近对话强署名格式与真人区分。
- [x] 图片附件上传与图片消息展示。
- [x] 前端乐观消息显示、跨天日期分隔、消息时间戳。
- [x] 前端手机响应式补充规则已存在于 `styles.css`。
- [x] 角色卡编辑与角色关系状态字段已接入。
- [x] Mem0MemoryStore 代码存在，失败时回退 SQLite；SQLite 仍作为兼容缓存。
- [ ] `SQLiteToolStore.reorder_todos()` 当前不改变物理顺序，只保留接口兼容。
- [ ] 主动提醒是保守实现：只按带 `due_time` 的 pending todo 生成固定提醒，不做复杂日程判断。
- [ ] 工具侧未接 Vikunja / Super Productivity，仍是自建 SQLiteToolStore。
- [ ] 前端组件未拆分，仍集中在 `App.jsx`。

### 关键接口边界

```python
# backend/chat/agents.py
def run_persona_agent(...) -> tuple[list[str], list[dict[str, Any]]]
def parse_reply_segments(raw: str | None) -> list[str]
```

```python
# backend/presence/policy.py
class InterjectionPolicy:
    def generate_reply(self, ctx: PresenceContext) -> Optional[list[str]]
```

```python
# backend/chat/context_assembler.py
def owner_private_scope_key(user_id: int, persona_id: int) -> str

def assemble_group_presence_context(
    session: Session,
    channel: Channel,
    persona: Persona,
    recent: list[Message],
    cfg: dict[str, str],
    mentioned_member_ids: list[int] | None = None,
) -> AssembledContext

def assemble_channel_context(
    session: Session,
    channel: Channel,
    persona: Persona,
    recent: list[Message],
    profile: ScopeProfile,
    cfg: dict[str, str],
) -> AssembledContext
```

```python
# backend/chat/service.py
class ChatService:
    def persist_persona_reply(self, channel_id: int, persona: Persona, reply_text: str | list[str]) -> list[MessageRead]
    def reply_chunks(self, persona: Persona, text: str | list[str], channel_type: str = "group") -> list[str]
```

```python
# backend/steward/service.py
class StewardService:
    def run_for_user_message(self, channel_id: int, recent: list[Message], user_content: str, persona_names: dict[int, str]) -> None
    def apply_tool_calls(self, channel_id: int, calls: list[dict[str, Any]], steward: Persona | None = None, recent: list[Message] | None = None) -> None
    def run_dock_message(self, channel_id: int, recent: list[Message], user_content: str, persona_names: dict[int, str]) -> dict[str, Any]
```

### 扫描备注

- 后端扫描：34 个 `.py` 文件；PowerShell 环境中 `find backend -type f -name "*.py"` 会命中 Windows `find`，本次用等价 `Get-ChildItem -Recurse -Filter *.py` 扫描。
- 前端扫描：2 个 `frontend/src` 文件。
- 数据库 schema：`sqlite3 app.db ".schema"` 执行成功，`personas.kind` 与 `creator_user_id` 已出现在 schema。
- API 路由扫描：发现 45 条 `@router.*` 路由，新增 `POST /api/personas/{persona_id}/clone`。
- 必跑检查：`python -m compileall backend scripts` 通过；`python scripts/smoke_two_users.py` 通过。
- 前端未修改，未运行 `npm run build`。
