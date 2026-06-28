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
