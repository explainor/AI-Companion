# 项目更新日志

本文件记录每次较大改动的依据、范围和验证结果。后续更新优先追加到顶部，方便回看构建脉络。

## 2026-06-24 - 三栏独立滚动

### 依据

- 用户反馈：前端左中右三栏滚动应当分离，各自可独立滑动。

### 改动

- 锁定 `html/body/#root` 为视口高度，禁止整页滚动。
- 左侧频道栏内容区改为独立滚动。
- 中间聊天工作区固定高度，消息区由 chatscope 独立滚动。
- 右侧事项模块改为独立滚动。
- 调整 `min-height: 0` 与 `overflow`，避免 CSS Grid 子项撑开父容器。

### 验证

- `npm.cmd run build` 通过。

## 2026-06-24 - 一键启动脚本

### 依据

- 用户反馈：每次需要手动输入地址和启动命令，使用成本太高。

### 改动

- 新增 `启动应用.bat`。
- 新增英文别名 `start_app.bat`。
- 新增 `start_app.ps1`，负责检测端口并避免重复启动。
- 双击脚本后会：
  - 启动 FastAPI 后端：`127.0.0.1:8000`
  - 启动 Vite 前端：`127.0.0.1:5173`
  - 自动打开浏览器到 `http://127.0.0.1:5173/`

## 2026-06-24 - 管家 Dock、SSE Typing/分条与主动 Tick

### 依据

- 继续推进 `companion_agent_v4_spec.md` 中上一轮未完成项。
- 用户要求不要搁置 V4 后续能力。

### 后端改动

- 新增管家 dock 系统频道：
  - `channels.type = steward`
  - `channels.is_system = 1`
  - 启动 seed 时自动创建并置顶。
  - 系统频道不可删除沿用会话管理限制。
- 管家前台对话：
  - 用户在管家 dock 频道发消息时，由管家回复。
  - 管家仍会通过后台 steward 逻辑检查并维护工具侧账本。
  - 默认前台口吻为简洁秘书式回复。
- SSE typing 与分条：
  - 角色回复会按段落/句子拆成多条消息。
  - 每条消息发送前通过 SSE 推送 `typing` 事件。
  - 延迟受 `sim.enabled`、`sim.min_delay_ms`、`sim.max_delay_ms` 和每角色 `sim_config` 控制。
- 主动 tick 接通：
  - `POST /api/steward/proactivity/tick` 不再只是占位。
  - 若没有带时间的未完成待办，则跳过提醒与模型调用。
  - 若有候选待办，则推送提醒到管家 dock。
  - 后端启动时创建保守心跳任务，只有 `proactivity.enabled=true` 时才运行。

### 前端改动

- 新增右下角「管家」dock 按钮。
- 点击 dock 按钮切换到管家系统频道。
- 前端监听 active channel 的 `message` / `typing` / `proactive` SSE 事件。
- 当前不在管家频道时，单独监听管家频道事件；有主动消息时 dock 按钮显示未读红点。

### 验证

- `python -m compileall backend` 通过。
- `npm.cmd run build` 通过。
- 管家 dock 频道自动创建回归通过。
- 管家 dock 对话回归通过。
- 主动 tick 有候选待办时推送到 dock 回归通过。

## 2026-06-24 - V4 标准家具、SSE 地基与时间上下文

### 依据

- `companion_agent_v4_spec.md`
- 用户要求继续按 V4 需求改造。

### 后端改动

- 扩展数据模型并做 SQLite 自动迁移：
  - `messages.status`
  - `messages.chunk_group`
  - `todos.priority`
  - `todos.notes`
  - `todos.repeat_rule`
  - `todos.source`
  - `channels.is_system`
  - `channels.pinned`
  - `channels.archived`
- 补齐 `ToolStore`：
  - `delete_todo`
  - `reorder_todos`
  - 扩展 `create_todo/update_todo` 支持 priority、notes、repeat_rule、source。
- 新增用户侧 Todo CRUD API：
  - `POST /api/todos`
  - `PATCH /api/todos/{todo_id}`
  - `DELETE /api/todos/{todo_id}`
  - `POST /api/todos/reorder`
  - `GET /api/todos?status=&sort=&priority=`
- 新增会话管理 API：
  - `PATCH /api/channels/{channel_id}`
  - `DELETE /api/channels/{channel_id}`
  - `DELETE /api/channels/{channel_id}/messages`
- 新增 Transport/SSE 地基：
  - `backend/core/transport.py`
  - `GET /api/channels/{channel_id}/events`
  - 当前消息写入后会通过 SSE 推送 `message` 事件。
- 新增统一时间上下文：
  - `backend/core/time_context.py`
  - 角色和管家 agent 调用都会注入当前时间、时段、频道间隔、角色发言间隔。
- 新增 `LLM_FORCE_FALLBACK=1` 开关，便于测试和调试时强制不调用真实模型。

### 前端改动

- 连接当前频道 SSE：
  - 接收 `message` 事件并更新聊天框。
  - 保留 REST 发送路径作为兼容。
- 消息显示增强：
  - 跨天日期分隔。
  - 每条消息显示时间。
  - 用户消息显示发送中 / 已送达 / 失败状态。
- 右侧 Todo 面板升级：
  - 用户可直接新增待办。
  - 可编辑 title、due、priority、notes、repeat_rule。
  - 可勾选完成 / 取消完成。
  - 可删除待办。
  - 支持按状态筛选、按创建/due/优先级排序。
  - 显示用户添加 / 管家添加来源。
- 顶部频道操作：
  - 群聊重命名。
  - 清空当前频道消息。
  - 删除非系统频道。

### 保留未完成项

- SSE 已接通基础 `message` 事件，但拟真分条、typing 延迟、主动提醒 dock 还未完整接入。
- 管家 dock 系统频道尚未做前台 UI。
- 主动心跳仍保持保守占位，未自动发提醒。

### 验证

- `python -m compileall backend` 通过。
- `npm.cmd run build` 通过。
- Todo CRUD 回归通过。
- 频道重命名、清空、删除回归通过。
- 群聊无 `@` 广播回归通过。
- 原健身链路回归通过。

## 2026-06-24 - 聊天发送体验与群聊默认路由调整

### 依据

- 用户反馈：发送消息后，自己的消息没有立即显示，而是等对方回复后一起出现。
- 用户要求：群聊中如果没有明确 `@某个人`，默认按未指定对象处理。

### 改动

- 前端发送消息时增加乐观显示：
  - 用户按发送后，自己的消息立即插入当前聊天框。
  - 后端返回后再用真实消息列表刷新。
  - 如果请求失败，则移除本地临时消息并显示错误。
- 群聊路由调整：
  - 有 `@角色名` 时，仅被点名角色回复。
  - 没有 `@角色名` 时，默认视为对群里所有普通角色广播，群成员都可回复。
- 群聊输入框 placeholder 更新为“不 @ 时默认发给群里所有角色”。

### 验证

- `npm.cmd run build` 通过。
- API 回归通过：群聊无 `@` 时，兄弟和老师都会回复。

## 2026-06-24 - V3 架构升级与 SJTU 模型配置

### 依据

- `companion_agent_v3_spec.md`
- 用户要求初始化 Git 仓库
- 用户提供 SJTU OpenAI-compatible API base 与可用模型调用名

### 后端改动

- 初始化 Git 仓库，并新增 `.gitignore`。
- 将后端从单文件业务逻辑拆分为 V3 目录结构：
  - `backend/core/`：配置、LiteLLM 调用封装、接口定义。
  - `backend/chat/`：频道、消息、角色回复、角色记忆。
  - `backend/tools/`：工具侧 `ToolStore` SQLite 实现。
  - `backend/steward/`：管家 agent 与工具侧写入编排。
  - `backend/api/`：FastAPI 薄路由。
- 新增接口边界：
  - `ToolStore`
  - `MemoryStore`
  - `ChatService`
- 模型与角色解绑：
  - `personas.model` 废弃。
  - 新增 `model_role`、`model_override`、`sim_config`。
  - 新增 `settings` 表管理模型档位。
- 管家升级为系统角色：
  - 使用 `is_system=1` 标记。
  - 工具侧写操作收束到 `steward/`。
- 新增数据留位：
  - `persona_state`
  - `habits`
  - `habit_logs`
- 新增 API：
  - `GET /api/settings`
  - `PUT /api/settings/{key}`
  - `GET /api/habits`
  - `GET /api/persona-state`
  - `POST /api/steward/proactivity/tick`
- 配置 SJTU 模型：
  - `OPENAI_API_BASE=https://models.sjtu.edu.cn/api/v1`
  - `model.chat_strong=openai/deepseek-chat`
  - `model.chat_cheap=openai/qwen3.5-27b`
  - `model.steward=openai/deepseek-chat`

### 前端改动

- 接入 `@chatscope/chat-ui-kit-react` 作为聊天 UI。
- 接入 Radix Dialog / Collapsible，形成可折叠侧栏和后台侧滑面板。
- 备忘录从常驻右栏移动到「后台」面板。
- 右侧常驻区保留「事项模块」。
- 新增「设置」面板，可编辑模型档位等配置项。

### 保留未实现项

按 V3 文档第 9 节要求，以下只做接口或配置留位，未擅自实现产品策略：

- 主动提醒由哪个角色、在哪个频道发声。
- 角色关系状态的具体字段扩展和演变规则。
- 管家跨频道识别、槽位补全、完成检测的 prompt 调优策略。
- 仿真 harness 的最终默认参数。
- 工具侧是否最终接 Vikunja / Super Productivity。

### 验证

- `python -m compileall backend` 通过。
- `npm.cmd run build` 通过。
- 回归链路通过：
  - `下午去健身`
  - `下午两点`
  - `跑了pb`
- 群聊点名回归通过：
  - `@老师 这个研究设计怎么改`
  - 仅老师回复。
- 后端重启后 `/api/settings` 正常返回 SJTU 模型配置。

## 2026-06-24 - V2 模型层改为 LiteLLM

### 依据

- `companion_agent_mvp_spec_v2.md`

### 改动

- 模型调用从 Anthropic SDK 改为 LiteLLM。
- 增加 `MODEL_CHEAP` / `MODEL_STRONG` 形式的模型档位思路。
- 保留本地 fallback，用于无 API key 时跑通验收链路。
- 前后端 MVP 能跑通：
  - 私聊兄弟。
  - 群聊 `@老师` 点名。
  - 管家维护 todo / memo。

### 验证

- API 级验收通过。
- 前端构建通过。

## 2026-06-24 - 初版 MVP 构建

### 依据

- `companion_agent_mvp_spec.md`

### 改动

- 搭建 FastAPI + SQLite + SQLModel 后端。
- 搭建 Vite + React 前端。
- 实现基础数据表：
  - `personas`
  - `channels`
  - `channel_members`
  - `messages`
  - `persona_notes`
  - `todos`
  - `memos`
- 种子数据：
  - 兄弟
  - 老师
  - 管家
  - 兄弟 DM 频道
- 实现核心消息循环：
  - DM 自动回复。
  - 群聊只响应 `@角色名`。
  - 管家静默维护事项和备忘录。

### 验证

- `下午去健身`、`下午两点`、`跑了pb` 链路跑通。
- 群聊点名冒烟通过。
