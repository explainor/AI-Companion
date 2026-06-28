# Companion Agent — Admin Panel & Member UX 修复版需求文档

> 给 Codex 的自包含执行规格。未提及的内容不动；遇到模糊点用工程常识处理，不自行扩大范围，不破坏已有架构边界。

---

## 0. 本版定位

**依据**：CONTEXT.md（2026-06-28 快照）+ 上游对话需求。

**本版要做的事（三个正交任务）：**

1. **后台管理界面**：引入 `starlette-admin`，挂载到 `/admin`，实现管理员登录保护，开放娱乐 AI 管理和全局系统配置两个管理视图。
2. **成员入群 UX 修复**：群聊界面的"添加成员"改为下拉选人面板（点 + 号），只显示**当前用户有权添加的成员**，管家 AI 和娱乐 AI 的可见性规则见 §4。
3. **权限修复**：普通用户不得编辑/添加他人的 `owned` AI 和 `entertainment` AI（除克隆外）；API 层加守卫。

**明确不动**：`ScopeProfile` 逻辑、`context_assembler.py`、presence/metrics、steward 分析钩子、记忆写入时序、强署名格式、smoke 测试脚本。

---

## 1. 架构总原则

### 后台管理：starlette-admin（不是 fastapi-amis-admin）

选型依据：
- **starlette-admin** 直接支持 SQLModel，原生 FastAPI/Starlette 挂载，MIT 许可，维护活跃，无需引入 Amis（百度 Amis 是另一个生态依赖，偏重）。
- **挂载方式**：`admin.mount_to(app)`，与现有 FastAPI 应用完全并列，不侵入任何现有路由。
- **认证方式**：`starlette-admin` 内置 `AuthProvider` 接口；实现一个基于 `settings` 表中 `admin.password_hash` 的简单 BasicAuth provider，密码用 bcrypt 散列。不引入 JWT，不新建用户表——管理员是单一全局账号，走 `settings` 表存 hash。

### 成员 UX：前端重构，API 不新增路由

现有 `GET /api/channels/{channel_id}/members` 和 `GET /api/personas` + `GET /api/users` 已足够。前端侧组装"可添加成员"列表，逻辑见 §4。

### 权限守卫：API 中间件层，不散落业务代码

在 `backend/api/routes.py` 为 PATCH/DELETE persona 路由统一加 `require_persona_owner` 依赖，不在各处各自判断。

---

## 2. 模块选型

| 模块 | 选型 | 判定 | 理由 |
|------|------|------|------|
| Admin 框架 | `starlette-admin[full]` | **adopt** | 原生 SQLModel 支持，MIT，轻量，直接挂 FastAPI |
| 密码散列 | `bcrypt`（已有 passlib 或直接 bcrypt） | **adopt** | 标准轮子，无需新依赖系统 |
| 管理员 Auth | 自建 SimpleAuthProvider（50 行） | **build** | starlette-admin AuthProvider 接口极薄，自建比引入第三方 OAuth 更合适当前规模 |
| 成员选人 UI | 自建下拉面板组件 | **build** | 纯前端逻辑，没有对应轮子 |

---

## 3. 数据模型变更

### 3.1 `settings` 表新增两条 key（幂等 seed）

```
admin.password_hash   # bcrypt hash，初始值为 hash("admin123")，首次部署后提示修改
admin.username        # 明文，默认 "admin"
```

用现有 `PUT /api/settings/{key}` 路由修改（此路由已存在，但**管理员密码修改只能在 /admin 界面内完成，不暴露给普通用户**——见 §4 权限规则）。

### 3.2 `personas` 表 —— 不新增列

`kind`（entertainment / owned / system）已存在，`creator_user_id` 已存在，足够。

### 3.3 不新增表

---

## 4. 接口 / 组件定义

### 4.1 starlette-admin 挂载

```python
# backend/main.py 末尾追加（在 app 路由注册后）

from starlette_admin.contrib.sqlmodel import Admin, ModelView
from backend.admin.auth import AdminAuthProvider
from backend.admin.views import EntertainmentPersonaView, SettingsView

admin_site = Admin(
    engine,
    title="Companion Admin",
    auth_provider=AdminAuthProvider(),
    base_url="/admin",
)
admin_site.add_view(EntertainmentPersonaView())
admin_site.add_view(SettingsView())
admin_site.mount_to(app)
```

新建 `backend/admin/` 包：

```
backend/admin/
├── __init__.py
├── auth.py       # AdminAuthProvider：验 settings.admin.username / admin.password_hash
└── views.py      # EntertainmentPersonaView, SettingsView
```

#### `auth.py` 规格

```python
class AdminAuthProvider(AuthProvider):
    async def login(self, username, password, remember_me, request, response):
        # 从 settings 表取 admin.username / admin.password_hash
        # bcrypt.checkpw；失败抛 FormValidationError
        ...
    async def is_authenticated(self, request) -> bool:
        # 检查 session["admin_logged_in"] == True
        ...
    def get_admin_user(self, request) -> AdminUser:
        return AdminUser(username="admin")
    async def logout(self, request, response): ...
```

#### `views.py` 规格

**EntertainmentPersonaView**

- 暴露的 `Persona` 字段：`id`（只读）、`name`、`system_prompt`、`model`、`model_override`、`is_system`（只读）、`kind`（只读，恒为 entertainment）
- 过滤：`list_query` 加 `where(Persona.kind == "entertainment")`，管理员看不到 owned/system
- 操作：新建（kind 硬写为 entertainment，creator_user_id 设为 NULL 或官方用户 id）、编辑、软删除（`DELETE /api/personas/{id}` 已有）
- 禁止：修改 `kind`、`creator_user_id`、`is_system`

**SettingsView**

- 暴露的 `Settings` 行：key 在白名单内才显示
- 白名单（初始）：
  ```
  personas.max_extra_owned
  presence.max_segments_group
  presence.max_segments_dm
  presence.cooldown_seconds
  presence.interjection_probability
  admin.username
  admin.password_hash   # 显示为 password 输入框，保存时自动 bcrypt
  ```
- 其他 key 不出现（避免管理员误改内部状态）

---

### 4.2 API 权限守卫

在 `backend/api/routes.py` 新增依赖函数：

```python
def require_persona_editable(persona_id: int, x_user_id: int = Header(...), session = Depends(get_session)):
    """
    规则：
    - kind == "system"：任何人不可编辑（只有 admin 界面可改，且当前 admin 界面不暴露 system）
    - kind == "entertainment"：任何普通用户不可编辑（报 403），只能克隆
    - kind == "owned"：只有 creator_user_id == x_user_id 可编辑
    """
```

把此依赖注入到：
- `PATCH /api/personas/{persona_id}`
- `DELETE /api/personas/{persona_id}`
- `PATCH /api/personas/{persona_id}/card`
- `PATCH /api/personas/{persona_id}/model`

**克隆不受限**：`POST /api/personas/{persona_id}/clone` 已有，任何人可克隆 entertainment，保持不变。

---

### 4.3 成员入群 UX —— 前端面板

**触发**：群聊顶部栏或成员侧栏的 **`+` 图标按钮**（现有的添加成员入口替换为此交互）。

**面板行为**：点击 `+` 后弹出一个浮层/下拉面板，分两个标签：

**标签 A — 真人**
- 列出所有 `users`（除当前用户自己、除已在频道中的成员）
- 显示：头像占位 + display_name

**标签 B — AI**
- 分两组展示：

  **我的 AI**（kind=owned 且 creator_user_id == 当前用户，包括管家 kind=system）
  - 管家 AI 用特殊图标标识（⭐ 或 [管家] 标签），可被加入群聊
  - 其余 owned AI 正常展示

  **娱乐 AI**（kind=entertainment）
  - 展示所有 entertainment AI（这些是公共的）
  - 用户直接可添加（不需先克隆）

- **不展示**：他人的 owned AI（kind=owned 且 creator_user_id ≠ 当前用户）

**选人逻辑**：
- 点击列表项即调用 `POST /api/channels/{channel_id}/members`，添加后该成员从列表中消失（防重复）
- 已在频道中的成员不展示在面板里
- 面板内有搜索框（前端过滤，不需新接口）

**移除成员**：现有成员列表项旁加移除按钮，调用 `DELETE /api/channels/{channel_id}/members/{member_type}/{member_id}`，仅频道创建者或成员自身可移除（前端判断 `created_by_user_id`，API 层同步加守卫）。

---

## 5. 反屎山规约

- `backend/admin/` 内只处理管理界面逻辑，不调用 `chat/`、`steward/`、`presence/`。
- `require_persona_editable` 是唯一的 persona 编辑权限入口，不允许在其他地方散写同类判断。
- `starlette-admin` 通过 SQLModel engine 直接读写，不走 `/api/*` 路由（保持关注点分离）。
- 管理员 session 存 Starlette session（需在 `main.py` 加 `SessionMiddleware`，key 走 `settings` 或 env），不与用户 session 混用。
- 新 `backend/admin/` 包不得被 `backend/chat/`、`backend/steward/` 等包 import——单向依赖，admin 可 import models，反向禁止。

---

## 6. 构建顺序

### M1：后端权限守卫（无 UI 变化，风险最低）

1. 在 `routes.py` 实现 `require_persona_editable` 依赖并注入上述4个路由。
2. 跑 `python -m compileall backend scripts` + `python scripts/smoke_two_users.py`，确认不 break 现有流程。

### M2：starlette-admin 挂载

1. `pip install "starlette-admin[full]" bcrypt`（加到 requirements.txt）。
2. 新建 `backend/admin/__init__.py`、`auth.py`、`views.py`。
3. `seed.py` 幂等写入 `admin.username` + `admin.password_hash`（hash("admin123")）。
4. `main.py` 末尾挂载 admin_site（加 `SessionMiddleware`，secret_key 读 env `ADMIN_SESSION_SECRET`，无则随机生成并 warn）。
5. 验收：访问 `/admin` 跳转登录页，用 admin/admin123 登录可见两个 View，登出有效。

### M3：前端成员面板 UX

1. 删除/替换现有的"添加成员"入口，改为 `+` 按钮触发浮层面板。
2. 实现标签 A（真人）+ 标签 B（AI 分组）逻辑，含搜索框。
3. 已在频道的成员不出现在面板。
4. 现有成员列表加移除按钮（带权限判断）。
5. 跑 `npm run build` 无报错。

---

## 7. 验收

### 权限守卫
- [ ] 用户 A 无法 PATCH/DELETE 用户 B 的 owned AI（返回 403）。
- [ ] 任何普通用户无法 PATCH/DELETE entertainment AI（返回 403）。
- [ ] 用户 A 可克隆 entertainment AI 为自己的 owned AI（200）。
- [ ] system AI 无法通过普通 API 修改（403）。

### Admin 界面
- [ ] `/admin` 未登录时跳转登录页。
- [ ] 错误密码被拒绝。
- [ ] 登录后可见"娱乐 AI 管理"和"系统配置"两个视图。
- [ ] 娱乐 AI 视图中可新建（kind 自动 entertainment）、编辑 name/system_prompt/model、删除。
- [ ] 娱乐 AI 视图中看不到 owned 和 system 类型的 persona。
- [ ] 系统配置视图只显示白名单 key，可修改值并保存。
- [ ] 修改 admin.password_hash 时输入新密码，保存后 hash 更新，旧密码失效。
- [ ] `/admin` 路由对普通用户（无 session）不可访问。

### 成员面板
- [ ] 群聊界面点 `+` 弹出面板，分真人 / AI 两标签。
- [ ] AI 标签下"我的 AI"只显示当前用户的 owned AI 和管家 AI（管家有特殊标识）。
- [ ] AI 标签下"娱乐 AI"显示所有 entertainment 类型。
- [ ] 他人的 owned AI **不出现**在面板中。
- [ ] 已在频道中的成员不出现在面板中。
- [ ] 搜索框可过滤列表（前端过滤，无需 API）。
- [ ] 点击成员即加入频道，面板中该条目消失。
- [ ] 成员列表旁有移除按钮；非创建者移除他人时被拒绝（API 403，前端提示）。

---

## 8. 需人类确认 / 准备

### 需你确认后再动的

1. **管理员密码初始值**：Codex 会写 hash("admin123") 作为种子，部署后你需要手动通过 admin 界面修改。如果你想用其他初始值，部署前告诉我，我更新 seed。

2. **娱乐 AI 初始内容**：现有 `seed.py` 里已有一批 entertainment AI，Codex 不会动它们。如果想借这次迭代补充/修改初始角色，把内容给我，我加到 Instruction 里。

3. **`SessionMiddleware` 的 secret_key**：Codex 会读 env var `ADMIN_SESSION_SECRET`，没有则随机生成并打 warn。生产环境你需要在 ECS 上 `export ADMIN_SESSION_SECRET=<随机字符串>`，否则重启后 admin session 失效。

### Codex 自行决定、无需确认

- starlette-admin 的 UI 主题/颜色（用默认主题，不需要定制）。
- 面板的具体 CSS 样式（继承 styles.css 现有变量，不引入新 CSS 框架）。
- `SessionMiddleware` 挂载的位置（在 `app = FastAPI()` 后、路由注册前）。
