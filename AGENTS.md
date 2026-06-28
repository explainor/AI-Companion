# AGENTS.md

## 项目是什么
一个多真人 + 多 AI 的群聊实验平台：真人和 AI 体在共享频道里对话，用于测量群聊轮替动力学。核心玩法包括用户把自己名下的私人 AI 带进共享群（混合态）。后端 FastAPI，存储 SQLite，前端 React + Vite。

## 怎么跑 / 怎么测（确切命令）
- 启服务（本地）：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
- 启服务（服务器）：`uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- 后端语法检查：`python -m compileall backend scripts`
- 双人 smoke 测试（每次改完必跑）：`python scripts/smoke_two_users.py`
- 构建前端（改了前端才需要）：`cd frontend && npm run build`
- Python 依赖装在虚拟环境：`source .venv/bin/activate`（服务器）

## 约定（只列与默认不同、容易搞错的）
- prompt 的拼装集中在 `backend/chat/context_assembler.py`，禁止散落回 `policy.py` / `agents.py`。
- 装配逻辑禁止出现 `if persona.owner_user_id` 这类硬分支；公共/私人/混合一律由 ScopeProfile 决定。
- 反幻觉只靠作用域隔离、白板声明、事实边界原则——**禁止任何禁词黑名单**。
- 记忆写入（摘要/事实抽取）只能发生在 AI 回复落库并记录时间戳之后，绝不在"决定发言"和"发出消息"之间。
- 最近对话一律强署名格式：`显示名(真人|AI, id=N): 内容`。
- 可配置项（模型名、阈值、插话率、触发词等）走 config 层，禁止写死在业务代码或数据行里。

## 数据库 / 迁移（高风险，硬约束）
- 改表结构前必须先备份库文件，再改。
- 只允许加表 / 加列（可空或带默认值）/ 加索引。
- **禁止删列、删表、改列名**——会永久丢数据。需要"删"就软删（加 `active` / `deleted_at` 标记）。
- 迁移逻辑写在 `backend/db.py` 的 `migrate_sqlite()`，必须幂等（加列前先判断列是否存在，已存在则跳过）。
- 任何迁移先在库的副本上验证旧数据完好，再对真库执行。

## 禁止触碰 / off-limits
- `.env` 及任何持有密钥、密码的文件——禁止读取内容写进代码，禁止提交进仓库。
- 数据库文件（`*.db` / `*.db-wal` / `*.db-shm`）——禁止提交进仓库。
- 已通过验收的测试脚本——禁止删除或弱化；改代码导致测试失败应修代码，不是改测试。

## Git / 提交约定
- 一个能跑通的状态 = 一次 commit，message 用中文短句说清改了啥。
- 只做当前规格范围内的改动，diff 只落在约定文件里；不擅自重命名、删文件、改接口签名。
- 不确定的产品规则不要自己发明——搭接口/stub 并报告。

## 完成一项任务时
报告：改了哪些文件、跑了哪些检查（compileall / smoke / build）、对照规格验收项的结果。任一验收项未过即视为未完成。
