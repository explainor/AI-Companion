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

## 当前代码快照（Codex 最后更新：2026-07-02）

### 后端文件树

```text
backend/
├── __init__.py                         # 后端包标记。
├── agents.py                           # 兼容/历史 agent 入口，当前主要聊天 agent 在 backend/chat/agents.py。
├── main.py                             # FastAPI 应用入口；注册 API、SessionMiddleware、/admin、/uploads 和静态前端。
├── db.py                               # SQLite engine、session_scope、init_db 和幂等迁移 migrate_sqlite()。
├── models.py                           # SQLModel 表模型：用户、频道、成员、消息、角色卡、记忆、工具账本、指标等。
├── schemas.py                          # API 请求/响应 schema，含用户资料、消息、频道、角色、记忆和事项 schema。
├── seed.py                             # 启动种子数据：官方用户、娱乐角色、系统管家、settings、admin 默认账号。
├── admin/
│   ├── __init__.py                     # admin 包标记。
│   ├── auth.py                         # starlette-admin AuthProvider，基于 settings.admin.username/password_hash 登录。
│   └── views.py                        # 娱乐 AI 管理视图和系统配置白名单视图。
├── api/
│   ├── __init__.py                     # API 包标记。
│   └── routes.py                       # REST API 与 SSE 路由；用户资料/头像、附件上传、聊天、成员、记忆、设置等。
├── chat/
│   ├── __init__.py                     # chat 包标记。
│   ├── agents.py                       # 普通角色 LLM/tool-loop 调用；生成层返回消息段数组。
│   ├── archive_retrieval.py            # 历史消息检索触发、片段召回和检索 gate 日志。
│   ├── context_assembler.py            # prompt 上下文装配中心；ScopeProfile、最近对话强署名、事实/摘要/检索片段注入。
│   ├── media.py                        # 图片、音频、附件消息的文本标签和图片 data URL。
│   ├── membership.py                   # 频道成员增删、成员校验、AI 展示名、活跃成员查询。
│   ├── memory.py                       # 角色私有笔记搜索和 tool call 落库；mem0 兼容封装。
│   ├── relationship.py                 # PersonaState 熟悉度、last_interaction 和里程碑更新。
│   ├── scope.py                        # 公共/私人/混合 ScopeProfile 判定。
│   └── service.py                      # ChatService 主业务：发消息、SSE 推送、AI 选择、回复清洗、多段落库、消息/频道读模型。
├── core/
│   ├── __init__.py                     # core 包标记。
│   ├── config.py                       # settings 默认值、seed、get/set/list、模型解析。
│   ├── interfaces.py                   # 工具账本和 ChatService 抽象接口。
│   ├── llm.py                          # LiteLLM 调用、provider ready、token/成本计数。
│   ├── time_context.py                 # 当前时间和最近消息相对时间文本。
│   └── transport.py                    # SSE 连接管理与事件广播。
├── metrics/
│   ├── __init__.py                     # metrics 包标记。
│   └── service.py                      # 单区间群聊轮替指标；compare 路由已移除。
├── presence/
│   ├── __init__.py                     # presence 包标记。
│   ├── context.py                      # PresenceContext 数据结构。
│   ├── policy.py                       # AI 插话生成策略；禁止输出最近对话署名前缀/转录。
│   └── triggers.py                     # @/点名/冷却/概率/cheap gate 等触发器。
├── steward/
│   ├── __init__.py                     # steward 包标记。
│   ├── agent.py                        # 管家 LLM/tool-loop 入口，提示词注入 MEMORY_PREDICATES。
│   ├── predicates.py                   # 受控 memory_facts predicate、中文标签、分组和 update_behavior 常量。
│   └── service.py                      # 管家后台分析、dock 回复、主动提醒 tick、受控 facts 落库和 resolve_supersedes。
└── tools/
    ├── __init__.py                     # tools 包标记。
    └── sqlite_store.py                 # SQLiteToolStore：todo/memo/habit 工具账本实现。
```

### 前端文件树

```text
frontend/src/
├── App.jsx       # React 主入口与全部页面/面板组件；聊天、角色页、设置弹窗、账号资料、成员管理、事项/记忆/管家小窗。
└── styles.css    # 全局样式、聊天布局、侧栏、设置弹窗、头像图片、聊天气泡、附件/音频展示和响应式规则。
```

### 数据库表结构

| 表名 | 关键字段 | 用途 |
|---|---|---|
| `users` | `id`, `email`, `display_name`, `avatar_url`, `created_at` | 薄身份真人用户；登录找回走邮箱，稳定识别走 `id` / `X-User-Id`，昵称和头像可改。 |
| `personas` | `id`, `name`, `system_prompt`, `model`, `is_steward`, `is_system`, `model_role`, `model_override`, `sim_config`, `kind`, `creator_user_id` | AI/系统角色基础信息、角色分类与创作者归属。 |
| `persona_card` | `persona_id`, `owner_user_id`, `persona_core`, `self_identity`, `relationship_backstory`, `speaking_style`, `example_dialogues`, `world_info`, `voice`, `traits` | 结构化角色卡与私人 AI owner 信息。 |
| `persona_state` | `persona_id`, `familiarity`, `last_tone`, `last_interaction`, `last_interaction_at`, `milestones` | 角色关系状态与里程碑。 |
| `persona_notes` | `id`, `persona_id`, `content`, `updated_at` | 角色私有记忆/兼容缓存。 |
| `channels` | `id`, `type`, `title`, `created_at`, `is_system`, `pinned`, `archived`, `ai_enabled`, `created_by_user_id` | 私聊、群聊、管家系统频道。 |
| `channel_members` | `id`, `channel_id`, `member_type`, `member_id`, `persona_id`, `user_id`, `added_by_user_id`, `active`, `left_at` | 频道真人/AI 成员关系，支持软退出。 |
| `messages` | `id`, `channel_id`, `sender`, `persona_id`, `author_type`, `author_user_id`, `ai_enabled_snapshot`, `message_type`, `media_url`, `mime_type`, `file_name`, `content`, `created_at`, `status`, `chunk_group` | 聊天消息、图片/语音/文件附件、多段同组追踪和 AI 在场快照。 |
| `interjection_decisions` | `id`, `channel_id`, `created_at`, `considered`, `spoke`, `trigger_reason`, `suppressed_reason`, `latency_ms` | AI presence 插话决策日志。 |
| `todos` | `id`, `title`, `status`, `due_time`, `priority`, `notes`, `repeat_rule`, `source`, `result`, `source_channel`, `created_at`, `completed_at` | 待办账本。 |
| `memos` | `id`, `content`, `created_at` | 备忘录账本。 |
| `habits` | `id`, `name`, `schedule`, `created_at` | 习惯定义。 |
| `habit_logs` | `id`, `habit_id`, `value`, `ts` | 习惯打卡记录。 |
| `settings` | `key`, `value` | 应用配置、模型、presence、多段上限、自有 AI 配额、admin.username、admin.password_hash。 |
| `scope_summaries` | `id`, `scope_type`, `scope_key`, `content`, `last_message_id`, `updated_at` | 按作用域滚动摘要。 |
| `memory_facts` | `id`, `scope_type`, `scope_key`, `subject_type`, `subject_id`, `predicate`, `content`, `source_message_id`, `confidence`, `supersedes_id`, `created_at` | 作用域隔离结构化长期事实；新写入 predicate 由 `backend/steward/predicates.py` 受控。 |

### API 路由清单

```text
POST   /api/users
GET    /api/users
GET    /api/users/{user_id}
PATCH  /api/users/{user_id}
POST   /api/users/{user_id}/avatar
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
GET    /api/channels/{channel_id}/events
POST   /api/channels/{channel_id}/attachments
POST   /api/channels/{channel_id}/ai_enabled
GET    /api/channels/{channel_id}/metrics
GET    /api/todos
POST   /api/todos
PATCH  /api/todos/{todo_id}
DELETE /api/todos/{todo_id}
POST   /api/todos/reorder
GET    /api/memos
GET    /api/memory?include_superseded=false
GET    /api/memory/predicates
POST   /api/memory/facts
PATCH  /api/memory/facts/{fact_id}
DELETE /api/memory/facts/{fact_id}
PATCH  /api/memory/persona-notes/{note_id}
DELETE /api/memory/persona-notes/{note_id}
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

- [x] 双真人薄身份：邮箱用于登录/找回用户；`users.id`、`X-User-Id`、消息 `author_user_id` 和频道成员 `member_id` 作为稳定身份。
- [x] `POST /api/users` 支持邮箱登录/自动注册：传 `email` 时按规范化邮箱查找，存在则返回同一用户 ID，不用昵称识别。
- [x] 用户资料可修改：`PATCH /api/users/{user_id}` 支持昵称和头像 URL，且只能编辑当前 `X-User-Id` 对应用户。
- [x] 用户头像可上传：`POST /api/users/{user_id}/avatar` 保存到 `/uploads/avatars/user_{id}/...`，只接受 png/jpeg/gif/webp。
- [x] 频道成员、频道列表和历史消息读模型会返回真人 `avatar_url` / `author_avatar_url`，前端头像图片即时展示。
- [x] 设置弹窗包含账号资料表单、头像上传按钮、昵称保存、主题和主题色、退出登录。
- [x] `/admin` 挂载 starlette-admin，使用 Starlette SessionMiddleware 和 settings 表中的 admin.username/admin.password_hash 登录。
- [x] 普通 API persona 编辑守卫收紧：system 不可编辑，entertainment 不可编辑/删除，owned 仅 creator_user_id 对应用户可编辑/删除。
- [x] 聊天页右上角入口：群聊、事项、管家；分别以小窗打开频道管理、事项工作台和管家对话。
- [x] 群聊管理小窗：真人 / AI 双标签、搜索、已在频道成员过滤、点击即加入；同时承载 AI 在场/缺席与清空消息等频道级动作。
- [x] AI 面板分组：我的 AI 显示当前用户 owned 与 system 管家，娱乐 AI 显示全部 entertainment；他人 owned 不展示。
- [x] 成员移除 API 守卫：频道创建者可移除成员；真人可移除自己；AI owner 可移除自己的 AI；其他情况 403。
- [x] 群聊手打 `@成员名` 会在前端自动解析为 `mentioned_member_ids`；后端也会按频道 AI 展示名/原始名兜底解析。
- [x] 显式 @ 多个 AI 时，不受 `presence.max_ai_replies_per_turn=1` 的普通插话上限截断；普通随机插话仍走上限。
- [x] presence 生成提示禁止输出“姓名(真人|AI,...):”署名前缀或复述最近对话；落库前清洗误吐的上下文转录行。
- [x] 事项小窗内的“记忆”tab 提供结构化事实 `memory_facts` 和角色笔记 `persona_notes` 查看、刷新、编辑、删除管理界面。
- [x] `MEMORY_PREDICATES` 定义受控 predicate，每个包含 `label` / `group` / `update_behavior`。
- [x] 管家 `write_memory_fact` 写入路径校验 predicate 必须在词表内；overwrite 类 predicate 由 `resolve_supersedes()` 标记旧事实。
- [x] `/api/memory` 默认只返回有效 facts；`include_superseded=true` 可返回旧事实；每条 fact 返回中文 predicate 元数据。
- [x] 角色生成层返回消息段数组；保存时每段独立落库并推送，typing 延迟复用原机制。
- [x] SSE `message` / `typing` / `proactive` 事件推送。
- [x] 频道创建、重命名、清空消息、删除非系统频道。
- [x] 图片、语音和通用文件附件上传与展示；媒体消息进入最近对话文本化标签。
- [ ] `SQLiteToolStore.reorder_todos()` 当前不改变物理顺序，只保留接口兼容。
- [ ] 主动提醒是保守实现：只按带 `due_time` 的 pending todo 生成固定提醒，不做复杂日程判断。
- [ ] 工具侧未接 Vikunja / Super Productivity，仍是自建 SQLiteToolStore。
- [ ] 前端组件未拆分，仍集中在 `App.jsx`。

### 关键接口边界

```python
# backend/api/routes.py
def get_current_user(session: Session, x_user_id: str | None) -> User
def clean_avatar_url(value: str | None) -> str | None
def normalize_email(value: str | None) -> str | None
def get_user(user_id: int) -> User
def update_user(user_id: int, payload: UserUpdate, x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> User
async def upload_user_avatar(user_id: int, file: UploadFile = File(...), x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> User
async def upload_attachment(channel_id: int, file: UploadFile = File(...), x_user_id: str | None = Header(default=None, alias="X-User-Id"))
def post_message(channel_id: int, payload: MessageCreate, x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> list[MessageRead]
def get_memory_records(include_superseded: bool = Query(default=False), x_user_id: str | None = Header(default=None, alias="X-User-Id"))
```

```python
# backend/schemas.py
class UserRead(BaseModel): id: int; email: Optional[str]; display_name: str; avatar_url: Optional[str]; created_at: str
class UserUpdate(BaseModel): display_name/displayName/name, avatar_url/avatarUrl
class MessageRead(BaseModel): author_user_id, author_user_name, author_avatar_url, media fields
```

```python
# backend/chat/service.py
class ChatService:
    def handle_user_message(self, channel_id: int, content: str, user_id: int, message_type: str = "text", media_url: str | None = None, mime_type: str | None = None, file_name: str | None = None, mentioned_member_ids: list[int] | None = None) -> list[MessageRead]
    def read_channel(self, channel: Channel) -> ChannelRead
    def read_message(self, message: Message) -> MessageRead
    def maybe_interject(self, channel: Channel, recent: list[Message], mentioned_member_ids: list[int] | None = None) -> list[MessageRead]
    def resolve_mentioned_agent_member_ids(self, channel_id: int, content: str, explicit_member_ids: list[int]) -> list[int]
```

```python
# backend/chat/context_assembler.py
def owner_private_scope_key(owner_user_id: int, persona_id: int) -> str
def format_recent_messages(recent: list[Message], session: Session, persona_names: dict[int, str]) -> str
def _owner_private_memory_facts(session: Session, profile: ScopeProfile, persona: Persona) -> list[MemoryFact]
```

```jsx
// frontend/src/App.jsx
function rememberCurrentUser(user)
async function saveCurrentUser(fields)
async function uploadCurrentUserAvatar(file)
function SettingsDialog({ open, onOpenChange, currentUser, avatarInputRef, onSaveProfile, onUploadAvatar, theme, setTheme, accent, setAccent, onLogout })
function Avatar({ name, hue = 95, src = "" })
function normalizeChannel(channel)
function normalizeMessage(message)
function MemberSheet({ open, onOpenChange, channel, personas, users, currentUser, onAdd, onRemove, onToggleAI, onClear })
```

### 扫描备注

- 后端扫描：PowerShell `Get-ChildItem -Path backend -Recurse -File -Filter *.py`，当前 40 个 `.py` 文件。
- 前端扫描：`frontend/src/App.jsx`、`frontend/src/styles.css`。
- 数据库 schema：`sqlite3 app.db ".schema"` 执行成功；用户表当前包含 `email`、`avatar_url`，并有 `ix_users_email` 唯一索引。
- API 路由扫描：`rg -n "^@router\\.|^def |^async def |class .*\\(.*BaseModel|class .*\\(SQLModel" backend/...`；用户资料路由包括 `POST /api/users`、`PATCH /api/users/{user_id}`、`POST /api/users/{user_id}/avatar`。
- 本轮验证：迁移前已备份 `app.db.backup_20260702_104501`，并在副本验证加列/唯一索引不改变用户行数；`python -m compileall backend scripts` 通过；`python scripts/smoke_two_users.py` 通过；`npm.cmd run build` 通过；额外 TestClient 验证同一邮箱返回稳定用户 ID，昵称修改不改变 ID/email。
