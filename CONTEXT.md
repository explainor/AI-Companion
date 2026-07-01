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

## 当前代码快照（Codex 最后更新：2026-07-01）

### 后端文件树

```text
backend/
├── __init__.py                         # 后端包标记。
├── agents.py                           # 兼容/历史 agent 入口，当前主要聊天 agent 在 backend/chat/agents.py。
├── main.py                             # FastAPI 应用入口；注册 API、SessionMiddleware、/admin、uploads 和静态前端。
├── db.py                               # SQLite engine、session_scope、init_db 和幂等迁移 migrate_sqlite()。
├── models.py                           # SQLModel 表模型：用户、频道、成员、消息、角色卡、记忆、工具账本、指标等。
├── schemas.py                          # API 请求/响应 schema，含 MessageCreate.mentioned_member_ids、PersonaCardUpdate 等。
├── seed.py                             # 启动种子数据：官方用户、娱乐角色、系统管家、settings、admin 默认账号。
├── admin/
│   ├── __init__.py                     # admin 包标记。
│   ├── auth.py                         # starlette-admin AuthProvider，基于 settings.admin.username/password_hash 登录。
│   └── views.py                        # 娱乐 AI 管理视图和系统配置白名单视图。
├── api/
│   ├── __init__.py                     # API 包标记。
│   └── routes.py                       # REST API 与 SSE 路由集中入口；附件上传支持图片、音频和通用文件。
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
│   └── service.py                      # ChatService 主业务：发消息、SSE 推送、AI 选择、回复清洗、多段落库。
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
├── App.jsx       # React 主入口与全部页面/面板组件；聊天、角色页、设置弹窗、成员管理、事项/记忆/管家小窗。
└── styles.css    # 全局样式、聊天布局、侧栏、设置弹窗、右上角小窗、聊天气泡、附件/音频展示和响应式规则。
```

### 数据库表结构

| 表名 | 关键字段 | 用途 |
|---|---|---|
| `personas` | `id`, `name`, `system_prompt`, `model`, `is_steward`, `is_system`, `model_role`, `model_override`, `sim_config`, `kind`, `creator_user_id` | AI/系统角色基础信息、角色分类与创作者归属。 |
| `persona_card` | `persona_id`, `owner_user_id`, `persona_core`, `self_identity`, `relationship_backstory`, `speaking_style`, `example_dialogues`, `world_info`, `voice`, `traits` | 结构化角色卡与私人 AI owner 信息；`voice` 仍在库中，但前端角色页暂不展示，避免误解为 AI 语音能力。 |
| `persona_state` | `persona_id`, `familiarity`, `last_tone`, `last_interaction`, `last_interaction_at`, `milestones` | 角色关系状态与里程碑。 |
| `persona_notes` | `id`, `persona_id`, `content`, `updated_at` | 角色私有记忆/兼容缓存。 |
| `users` | `id`, `display_name`, `created_at` | 薄身份真人用户。 |
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
```

### Admin 挂载

```text
GET/POST /admin/login
GET      /admin/logout
GET      /admin/                         # starlette-admin 首页
GET      /admin/persona/list             # 娱乐 AI 管理视图，只列 kind=entertainment
GET      /admin/setting/list             # 系统配置白名单视图
GET      /admin                          # 精确重定向到 /admin/
```

### 功能完成状态

- [x] `/admin` 挂载 starlette-admin，使用 Starlette SessionMiddleware 和 settings 表中的 admin.username/admin.password_hash 登录。
- [x] 普通 API persona 编辑守卫收紧：system 不可编辑，entertainment 不可编辑/删除，owned 仅 creator_user_id 对应用户可编辑/删除。
- [x] 聊天页右上角入口：群聊、事项、管家；分别以小窗打开频道管理、事项工作台和管家对话。
- [x] 侧栏底部是设置入口；设置弹窗包含账号信息、外观配置，退出登录移动到设置页底部。
- [x] 聊天输入框上方快捷建议栏已移除，不再显示无意义快捷按钮。
- [x] 角色页移除“声音”字段展示；当前无 AI 语音能力，避免误导用户。
- [x] 群聊管理小窗：真人 / AI 双标签、搜索、已在频道成员过滤、点击即加入；同时承载 AI 在场/缺席与清空消息等频道级动作。
- [x] AI 面板分组：我的 AI 显示当前用户 owned 与 system 管家，娱乐 AI 显示全部 entertainment；他人 owned 不展示。
- [x] 成员移除 API 守卫：频道创建者可移除成员；真人可移除自己；AI owner 可移除自己的 AI；其他情况 403。
- [x] 群聊手打 `@成员名` 会在前端自动解析为 `mentioned_member_ids`；后端也会按频道 AI 展示名/原始名兜底解析。
- [x] 显式 @ 多个 AI 时，不受 `presence.max_ai_replies_per_turn=1` 的普通插话上限截断；普通随机插话仍走上限。
- [x] presence 生成提示禁止输出“姓名(真人|AI,...):”署名前缀或复述最近对话；落库前清洗误吐的上下文转录行。
- [x] 前端日期解析容错：中文自然语言时间、坏时间字段不会因 `toISOString()` 导致主页白屏；消息排序/日期分隔也使用安全日期函数。
- [x] 事项小窗内的“记忆”tab 提供结构化事实 `memory_facts` 和角色笔记 `persona_notes` 查看、刷新、编辑、删除管理界面。
- [x] `MEMORY_PREDICATES` 定义受控 predicate，每个包含 `label` / `group` / `update_behavior`。
- [x] 管家静默分析提示词注入受控词表、memory_facts vs todos/habits 边界、最多 3 条写入规则。
- [x] 管家 `write_memory_fact` 写入路径校验 predicate 必须在词表内；习惯不再同步写入 memory_facts。
- [x] overwrite 类 predicate 写入后由 `resolve_supersedes()` 将同 scope 同 predicate 的旧有效事实标记为 superseded。
- [x] state / accumulate 类 predicate 直接新增，不主动 supersede。
- [x] `/api/memory` 默认只返回 `supersedes_id IS NULL` 的 facts；`include_superseded=true` 可返回旧事实。
- [x] `/api/memory` 每条 fact 返回 `predicate_label`、`predicate_group`、`superseded`。
- [x] `/api/memory/predicates` 返回词表和分组顺序。
- [x] `/api/memory/facts` 支持手动创建 owner-private fact，并校验 predicate 词表。
- [x] `context_assembler.py` owner-private facts 注入过滤 superseded，按 `created_at DESC LIMIT 60` 控制 token 膨胀。
- [x] 前端记忆 tab 按词表分组顺序展示，fact 卡片显示中文 predicate 标签、content、置信度和日期。
- [x] 角色生成层返回消息段数组；保存时每段独立落库并推送，typing 延迟复用原机制。
- [x] SSE `message` / `typing` / `proactive` 事件推送。
- [x] Todo CRUD、完成、删除、reorder 接口占位兼容。
- [x] 频道创建、重命名、清空消息、删除非系统频道。
- [x] 双真人薄身份：`users` 表与 `X-User-Id`。
- [x] 群聊 AI 在场/缺席开关；催化剂读数 UI、`刷新 compare()` 和 `/metrics/compare` 已移除。
- [x] 图片附件上传与图片消息展示。
- [x] 聊天输入表情面板：点击表情按钮后插入 emoji 到当前输入框。
- [x] 通用文件上传：附件按钮可上传非图片文件，消息气泡显示文件名并可下载。
- [x] 语音消息：浏览器 `MediaRecorder` 录音后按音频附件发送，气泡内可直接播放。
- [x] 媒体上下文标签：图片、语音、附件分别进入最近对话文本化标签，避免 AI 看到空消息。
- [x] 无频道状态下频道相关按钮禁用：群聊管理和输入工具不会表现为“点了没反应”。
- [ ] `SQLiteToolStore.reorder_todos()` 当前不改变物理顺序，只保留接口兼容。
- [ ] 主动提醒是保守实现：只按带 `due_time` 的 pending todo 生成固定提醒，不做复杂日程判断。
- [ ] 工具侧未接 Vikunja / Super Productivity，仍是自建 SQLiteToolStore。
- [ ] 前端组件未拆分，仍集中在 `App.jsx`。

### 关键接口边界

```python
# backend/chat/service.py
class ChatService:
    def handle_user_message(self, channel_id: int, content: str, user_id: int, message_type: str = "text", media_url: str | None = None, mime_type: str | None = None, file_name: str | None = None, mentioned_member_ids: list[int] | None = None) -> list[MessageRead]
    def maybe_interject(self, channel: Channel, recent: list[Message], mentioned_member_ids: list[int] | None = None) -> list[MessageRead]
    def speaking_candidate_members(self, candidate_members: list[ChannelMember], mentioned_member_ids: list[int], cfg: dict[str, str]) -> list[ChannelMember]
    def resolve_mentioned_agent_member_ids(self, channel_id: int, content: str, explicit_member_ids: list[int]) -> list[int]
    def sanitize_persona_reply(self, text: str) -> str

def _text_mentions_agent(text: str, label: str) -> bool
def _looks_like_context_transcript(text: str) -> bool
```

```python
# backend/presence/policy.py
class InterjectionPolicy:
    def generate_reply(self, ctx: PresenceContext) -> Optional[list[str]]
```

```python
# backend/steward/predicates.py
MEMORY_PREDICATES: dict[str, dict]
PREDICATE_PROMPT_BLOCK: str
GROUP_ORDER: list[str]
```

```python
# backend/steward/service.py
def resolve_supersedes(session: Session, scope_type: str, scope_key: str, predicate: str, new_fact_id: int) -> None

class StewardService:
    def run_for_user_message(self, channel_id: int, recent: list[Message], user_content: str, persona_names: dict[int, str]) -> None
    def apply_tool_calls(self, channel_id: int, calls: list[dict[str, Any]], steward: Persona | None = None, recent: list[Message] | None = None) -> None
    def _write_owner_fact(self, steward: Persona | None, owner_user_id: int | None, predicate: str, content: str, source_message: Message | None, confidence: Any = None) -> bool
```

```python
# backend/api/routes.py
def can_access_memory_fact(fact: MemoryFact, user: User, channels: set[int]) -> bool
def memory_fact_payload(fact: MemoryFact, persona_names: dict[int, str], channel_names: dict[int, str]) -> dict
def get_memory_records(include_superseded: bool = Query(default=False), x_user_id: str | None = Header(default=None, alias="X-User-Id"))
def get_memory_predicates()
def create_memory_fact(payload: MemoryFactCreate, x_user_id: str | None = Header(default=None, alias="X-User-Id"))
async def upload_attachment(channel_id: int, file: UploadFile = File(...), x_user_id: str | None = Header(default=None, alias="X-User-Id"))
def post_message(channel_id: int, payload: MessageCreate, x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> list[MessageRead]
```

```python
# backend/metrics/service.py
def session_metrics(session: Session, channel_id: int, start: str | None = None, end: str | None = None) -> dict
def metrics_over(messages: list[Message], decisions: list[InterjectionDecision]) -> dict
```

```python
# backend/chat/media.py
def message_media_label(message: Message) -> str
def message_text_with_media(message: Message) -> str
def image_message_to_data_url(message: Message) -> str | None
```

```python
# backend/chat/context_assembler.py
def owner_private_scope_key(owner_user_id: int, persona_id: int) -> str
def format_recent_messages(recent: list[Message], session: Session, persona_names: dict[int, str]) -> str
def _owner_private_memory_facts(session: Session, profile: ScopeProfile, persona: Persona) -> list[MemoryFact]
```

```jsx
// frontend/src/App.jsx
function SettingsDialog({ open, onOpenChange, currentUser, theme, setTheme, accent, setAccent, onLogout })
function TopPopover({ title, onClose, className = "", children })
function MemberSheet({ open, onOpenChange, channel, personas, users, currentUser, onAdd, onRemove, onToggleAI, onClear })
function mentionedMemberIdsFromContent(content)
function textMentionsMember(text, label)
function parseLooseDate(value)
function safeDateValue(value)
function dateSortValue(value)
function dateLabelKey(value)
```

### 扫描备注

- 后端扫描：PowerShell `Get-ChildItem -Path backend -Recurse -File -Filter *.py`，当前 40 个 `.py` 文件。
- 前端扫描：`frontend/src/App.jsx`、`frontend/src/styles.css`。
- 数据库 schema：`sqlite3 app.db ".schema"` 执行成功；本轮未新增表/列。
- API 路由扫描：`rg -n "@router\.(get|post|patch|delete)|app\.(get|post|patch|delete)" backend`；`/api/channels/{channel_id}/metrics/compare` 已移除，`/api/channels/{channel_id}/metrics` 保留。
- 本轮关键验证：`python -m compileall backend scripts` 通过；`python scripts/smoke_two_users.py` 通过；`npm.cmd run build` 多次通过。
- 额外验证：显式多 @ 不再被普通回复上限截断；上下文转录格式可被识别并拦截；浏览器实际验证设置入口可打开，账号/外观/退出登录显示正确。
