# Companion Agent

本项目是一个本地/私有部署的 AI 伙伴聊天应用。当前版本实现了 v6 验证目标：一个频道里两个真人和一个默认沉默的共享 AI，通过 AI 在场/缺席对照观察群聊轮替动力学。

## 功能概览

- 多角色聊天：私聊、群聊、角色卡。
- 双真人频道：每个设备首次进入时选择名字，后端用 `X-User-Id` 区分真人身份。
- 默认沉默 AI：群聊中 AI 不再默认抢话，只在被 @、点名或通过 presence 闸门后偶发插话。
- 管家系统：维护待办、备忘录、习惯和主动提醒。

## 技术栈

- 后端：FastAPI + SQLModel + SQLite + LiteLLM + SSE
- 前端：Vite + React
- 数据库：SQLite 单文件，默认生成在项目根目录 `app.db`

## 不要上传到 GitHub 的内容

这些已经在 `.gitignore` 中排除：

- `.env`、`.env.*`：真实 API Key 和本地环境变量
- `app.db`、`*.db`：本地数据库和聊天记录
- `frontend/node_modules/`：前端依赖
- `frontend/dist/`：前端构建产物
- `.mem0/`、`chroma/`：本地向量存储
- `unused_files_20260626/`：历史归档和废弃文件
- `__pycache__/`、`.venv/`、日志和系统临时文件

可以上传的核心内容：

- `backend/`
- `frontend/src/`
- `frontend/index.html`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/vite.config.js`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `CONTEXT.md`
- `README.md`
- `CHANGELOG.md`
- `docs/specs/`
- `项目架构总结.md`
- `start_app.ps1`、`start_app.bat`、`启动应用.bat`

## 本地开发

安装后端依赖：

```powershell
pip install -r requirements.txt
```

安装前端依赖：

```powershell
cd frontend
npm install
```

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，填入你的模型 API Key。

启动应用：

```powershell
.\start_app.ps1
```

默认地址：

- 前端：`http://127.0.0.1:5173/`
- 后端：`http://127.0.0.1:8000/`

## 云服务器部署思路

服务器上需要安装：

- Python 3.10+
- Node.js 18+
- Git

拉取代码：

```bash
git clone <你的仓库地址>
cd <仓库目录>
```

准备后端：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，填入模型 API Key。

构建前端：

```bash
cd frontend
npm install
npm run build
cd ..
```

启动后端并托管构建后的前端：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

此时 FastAPI 会自动挂载 `frontend/dist`，浏览器访问：

```text
http://服务器IP:8000/
```

生产环境建议再加一层 Nginx、HTTPS 和进程守护（例如 systemd）。

## 双人测试方式

1. 你和朋友分别用自己的手机/电脑打开同一个部署地址。
2. 首次进入时各自输入不同名字。
3. 创建或进入同一个群聊频道。
4. 使用顶部 `AI 在场/AI 缺席` 切换做对照。
5. 使用顶部 `AI 在场/AI 缺席` 切换做对照观察。

当前身份系统是 v6 要求的“薄身份，无密码”。它适合熟人测试和小范围验证，不适合作为公开产品账号体系。

## 本地回归测试

每次改完双人频道、身份、presence 或 metrics 相关代码，先在本地跑：

```powershell
python scripts\smoke_two_users.py
python -m compileall backend scripts
cd frontend
npm run build
```

`smoke_two_users.py` 会创建两个临时用户、一个双人群聊和两条消息，然后检查：

- 两条真人消息是否分别写入不同的 `author_user_id`
- AI presence 上下文是否同时包含两个真人名字
- 最近对话是否按真实作者渲染

通过后再提交、推送、部署到服务器。
