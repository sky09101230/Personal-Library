# Personal-Library

从 PLAB Scientific Agent 演化的个人科研文献与 Skill 管理库。默认在 Windows 本机运行，使用 **Django / ASGI + SQLite + 本地文件存储**，网页地址为 `http://127.0.0.1:8001/`。

- 文献：PDF 上传、元数据确认、DOI 跳转、Zotero 导入、全文解析和下载。
- 阅读：AI Overview、Paper Skeleton、单篇 Paper Chat、对话历史和删除。
- 证据：结论引用原文片段，Figure 解读搭配原图、图注与 PDF 页入口。
- Skills：公开 GitHub 来源发现、候选审核、发布与文件预览。
- MCP：网页与 `/mcp` 共用 ASGI 服务，令牌控制文献/Skill 访问。

## 1. 准备环境与安装

建议使用 **Python 3.13**、Git 和 PowerShell。当前本地验证版本为 Python 3.13.5。基础运行不需要 Node.js、PostgreSQL、NAS 或向量数据库。

```powershell
git clone https://github.com/sky09101230/Personal-Library.git
cd Personal-Library
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

没有 `py` 命令时，可用 `python --version` 确认版本，再执行 `python -m venv .venv`。后续始终使用项目 `.venv` 的 Python，无需激活环境。Uvicorn 已显式列在依赖中。

## 2. 创建 `.env`：先启动基础功能

只在首次安装时复制模板，已有配置不要覆盖：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

用下面命令生成随机 Django 密钥，将输出粘贴到 `.env` 的 `DJANGO_SECRET_KEY=` 后面，不要公开它：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

基础本机配置如下。数据目录可换成你有写入权限的位置；没有 E 盘时必须更改：

```dotenv
DJANGO_SECRET_KEY=填入上一步生成的随机值
DJANGO_DEBUG=true
ALLOWED_HOSTS=127.0.0.1,localhost
MCP_PUBLIC_BASE_URL=http://127.0.0.1:8001
AGENTSYS_DB_ENGINE=sqlite
LITERATURE_STORAGE_BACKEND=local
LOCAL_STORAGE_ROOT=E:\Personal-Library\data
```

`LOCAL_STORAGE_ROOT=data` 也可使用项目下被 Git 忽略的 `data/`。SQLite 数据库固定保存在项目根目录的 `db.sqlite3`，`AGENTSYS_DB_NAME` 等 PostgreSQL 参数在 SQLite 模式下不生效。

此时先保留 `PAPER_LLM_BASE_URL`、`PAPER_LLM_API_KEY`、`PAPER_CHAT_MODEL`、`PAPER_OVERVIEW_MODEL` 和所有服务密钥为空，可以运行基础网页、文件管理和元数据确认。新正文默认入 MinerU 队列；未配置解析密钥时不会自动处理，后续第 5 节说明手动处理方法。

`.env` 采用简单 `KEY=value` 格式，每个参数只写一次；不要加 `export`，不要在值后加行内注释。进程已有环境变量优先于文件配置，修改文件后要重启网页和 worker。

## 3. 初始化并启动

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py check
.\start.ps1
```

打开 [本机首页](http://127.0.0.1:8001/)，用刚创建的账号登录。管理后台为 [本机 Admin](http://127.0.0.1:8001/admin/)。

`start.ps1` 会执行 Django check，在 `.env` 存在 `MINERU_API_TOKEN` 时启动单个后台文献 worker，再启动 Uvicorn。没有 token 时仅启动网页；启动脚本不会自动应用新增迁移。默认只绑定本机 `127.0.0.1`。

端口占用时可以换端口，并同步修改 `MCP_PUBLIC_BASE_URL`：

```powershell
.\start.ps1 -Port 8010
```

PowerShell 阻止脚本执行时，只对这一次启动使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

## 4. 启用 AI：配置模型接口

### 4.1 OpenAI-compatible 接口 / 本机 Cockpit

先启动自己的模型代理，并在代理管理界面确认 **API 根地址、认证 key、实际模型 ID**。本机使用过的地址为 `http://localhost:53347/v1`；这是示例，你的代理可能使用其它端口。

在 `.env` 填写完整的一组参数：

```dotenv
PAPER_LLM_BASE_URL=http://localhost:53347/v1
PAPER_LLM_API_KEY=填入代理提供的key
PAPER_CHAT_MODEL=gpt-6-sol
PAPER_OVERVIEW_MODEL=gpt-6-sol
PAPER_VISION_MODEL=
PAPER_LLM_REASONING_EFFORT=medium
PAPER_LLM_TIMEOUT=30
PAPER_LLM_RETRIES=1
PAPER_LLM_JSON_MODE=true
PAPER_LLM_VISION_ENABLED=false
PAPER_LLM_STREAMING_ENABLED=false
PAPER_SKELETON_TIMEOUT=180
PAPER_SKELETON_CONTEXT_BYTES=24000
PAPER_SKELETON_MAX_TOKENS=2560
PAPER_SKELETON_FALLBACK_CONTEXT_BYTES=18000
```

`gpt-6-sol` 是本机代理曾实际提供并验证的模型 ID，**并非所有代理都有**；请用你的代理 `/models` 列表或管理界面提供的准确名称，不能直接把显示名称（例如“GPT 6.1 Sol medium”）当 API 模型 ID。`medium` 单独配置在 `PAPER_LLM_REASONING_EFFORT`，不拼接在模型名后。

| 参数 | 用途 / 注意事项 |
| --- | --- |
| `PAPER_LLM_BASE_URL` | API 根地址，客户端追加 `/chat/completions`；填 `/v1` 根路径，不要填完整 completions URL |
| `PAPER_LLM_API_KEY` | 服务端认证密钥；本地无认证代理可空，是否必需由代理决定 |
| `PAPER_CHAT_MODEL` | Chat / 检索问题改写的模型 ID |
| `PAPER_OVERVIEW_MODEL` | AI Overview / Paper Skeleton 的模型 ID；与 Chat 一起配置 |
| `PAPER_VISION_MODEL` | 可选视觉模型 ID；默认不填。配置视觉 Provider 不表示每次 Skeleton 都读取图片像素，当前图示解读主要依据图注/正文 |
| `PAPER_LLM_REASONING_EFFORT` | 代理支持时使用的推理强度，如 `medium`；不支持该参数的代理需适配 |
| `PAPER_LLM_TIMEOUT` / `PAPER_LLM_RETRIES` | 普通模型请求超时秒数 / 最多一次额外重试；不要把模型超时当浏览器加载进度 |
| `PAPER_LLM_JSON_MODE` | 模型支持 JSON mode 时保持 true；关闭只省略 response_format，后端仍严格校验 JSON 和证据 |
| `PAPER_LLM_VISION_ENABLED` | 是否允许视觉 Provider 输入，需同时配置视觉模型 |
| `PAPER_LLM_STREAMING_ENABLED` | 保留的能力配置；当前阅读器等待验证完成再显示回答，不展示未校验 token 流 |
| `PAPER_SKELETON_TIMEOUT` | 总览单次请求超时，默认 180 秒，可设 1–300；代理自身超时仍可能更短 |
| `PAPER_SKELETON_CONTEXT_BYTES` | 总览输入预算，默认 24000 UTF-8 字节；过小无法保留章节/图注时会明确报错 |
| `PAPER_SKELETON_MAX_TOKENS` | 总览输出上限，默认 2560，可设 512–4096；调大可能增加耗时，不保证更好的结论 |
| `PAPER_SKELETON_FALLBACK_CONTEXT_BYTES` | 传输失败后一次紧凑重试预算，默认/上限 18000；须小于初次输入预算 |

地址默认要求 HTTPS，仅允许精确的 loopback HTTP 地址（localhost、127.0.0.1、::1），不允许公网或局域网 HTTP。模型地址和 key 只在服务器 `.env` 中配置，不向浏览器暴露。

如果启用 PAPER 配置，必须同时填 API 根、Chat 和 Overview 模型；缺项会报配置错误，不会自动混用 DeepSeek key。只使用 DeepSeek 时，将上述四个必需 PAPER 字段都留空。

### 4.2 DeepSeek（可选）

书目元数据 AI 建议、Skill 摘要仍使用 DeepSeek 配置，不会因为配置 PAPER 接口自动切换。旧 AI Overview 在未设置 `PAPER_OVERVIEW_MODEL` 时也使用 DeepSeek。

```dotenv
DEEPSEEK_API_KEY=填入自己的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=填入账号实际支持的模型ID
DEEPSEEK_TIMEOUT=30
```

`DEEPSEEK_OVERVIEW_MODEL` 可覆盖旧 Overview 模型。`AI_API_KEY` 为历史预留字段，当前这几条 AI 路径不读取它。

## 5. 启用解析与阅读

### 5.1 MinerU（推荐用于图表、公式与结构化解析）

在 [MinerU API 管理](https://mineru.net/apiManage) 获取 token，填入 `.env`：

```dotenv
MINERU_API_TOKEN=填入自己的MinerU token
MINERU_MODEL_VERSION=vlm
MINERU_REQUEST_TIMEOUT=120
MINERU_POLL_INTERVAL=5
MINERU_POLL_TIMEOUT=3600
MINERU_SEGMENT_PAGES=200
MINERU_RESULT_MAX_BYTES=838860800
```

解析会把 PDF 发到 MinerU 服务；原始 PDF 和派生解析结果仍分开保存。重启启动脚本后，worker 会处理已入队的正文。

1. 文献库 → 上传 PDF → 校对标题、作者、期刊和 DOI → 确认入库。
2. 打开“文献详情”，查看解析状态；AI Overview 用已配置的模型生成。
3. 默认第一页是“文献信息 / AI Overview”。文献库 AI 标签来自该 Overview 的 topics，超过 3 个可展开。
4. 切换“Paper Intelligence · 智能阅读”，生成/重新生成 Skeleton，或在 Chat 中提问当前论文。
5. 点击 Evidence 查看来源；图示解读含原图、图注、放大与 PDF 页入口。模型回答/解析本身仍可能出错，重要结论应核对原文。
6. Chat 历史可切换、新建；悬停历史条目右上角 `×`，确认后删除该对话和消息。

查看队列 / 手动处理：

```powershell
.\.venv\Scripts\python.exe manage.py plab literature status
# 上传记录ID（UploadedDocument ID），不是规范文献ID或Parse ID
.\.venv\Scripts\python.exe manage.py plab literature enqueue --upload-id 12 --parser mineru --force
# 未运行后台worker时，在另一终端前台运行，Ctrl+C可停止
.\.venv\Scripts\python.exe manage.py plab literature worker
```

### 5.2 仅使用 PyPDF

PyPDF 不需要 MinerU token，但不能得到同等的 Figure/版面结构，扫描 PDF 可能没有可提取文本。上传自动队列默认是 MinerU，切换为 PyPDF 需手动入队：

```powershell
.\.venv\Scripts\python.exe manage.py plab literature enqueue --upload-id 12 --parser pypdf --force
.\.venv\Scripts\python.exe manage.py plab literature worker --once
```

已有活动任务时 enqueue 会复用它；用 `status` 确认任务和 parser，不要重复启动多个 worker。PyPDF 无外部解析调用，但后续 AI Overview 仍需要 PAPER 或 DeepSeek 模型配置。

## 6. 其它服务与高级参数

未启用对应功能时，可保留 `.env.example` 默认值或空密钥。

| 配置 | 用途 |
| --- | --- |
| `MCP_MAX_UPLOAD_BYTES` | 上传字节上限，默认 104857600（100 MiB） |
| `METADATA_HTTP_TIMEOUT` | DOI/Crossref 查询超时，默认 15 秒 |
| `DOI_RESOLVER_URL` / `CROSSREF_API_URL` / `CROSSREF_MAILTO` | DOI 与 Crossref 元数据接口；邮箱可选 |
| `ZOTERO_API_URL` | Zotero API 根；账号连接在网页 Zotero 设置中完成 |
| `GITHUB_API_TOKEN` | 公开 Skill 搜索/扫描；只授予所需公开资源读取权限 |
| `LITERATURE_DOWNLOAD_LINK_MAX_AGE` / `SKILL_DOWNLOAD_LINK_MAX_AGE` | 签名下载链接有效秒数，默认 300 |
| `SKILL_JOB_STALE_SECONDS` | Skill 任务过期阈值，默认 3600 秒 |
| `MINERU_API_BASE_URL` | 官方解析 API 根，默认 https://mineru.net/api/v4 |
| `MINERU_REALTIME_API_TOKEN` | 可选多通道实时 token；通道解析时回退到 MINERU_API_TOKEN |
| `MINERU_BACKFILL_API_TOKEN_1` 至 `MINERU_BACKFILL_API_TOKEN_4` | 可选 worker-pool 四条回填通道 token；本机单 worker 无需填写 |

若实际需要多通道，配置一个实时 token 和四个互不重复的回填 token，再运行 `manage.py plab literature worker-pool`。不要把单 worker 和 pool 重复用于同一部署。

### NAS 与 PostgreSQL（以后再启用）

本机保持 SQLite + local 即可；后端仍支持 `LITERATURE_STORAGE_BACKEND=nas_webdav`。NAS 参数为 `NAS_WEBDAV_BASE_URL`、`NAS_WEBDAV_USERNAME`、`NAS_WEBDAV_PASSWORD`、`NAS_WEBDAV_LITERATURE_ROOT`、`NAS_WEBDAV_SKILLS_ROOT`、`NAS_WEBDAV_SKILL_CANDIDATES_ROOT`。当前 NAS adapter 有既有证书校验例外，接入前请核实部署边界，不把它用于任意不可信服务。

PostgreSQL 使用 `AGENTSYS_DB_ENGINE=postgresql` 及 `AGENTSYS_DB_NAME`、`AGENTSYS_DB_USER`、`AGENTSYS_DB_PASSWORD`、`AGENTSYS_DB_HOST`、`AGENTSYS_DB_PORT`。**仅修改这些参数不会转移 SQLite 数据**；迁移必须保留主键、parse / Evidence 身份，先备份、停写、试迁和回归。步骤见 [SQLite-first 决策](docs/decisions/0046-paper-intelligence-sqlite-first.md)。

### MCP / Skills 管理

MCP 地址为 `http://127.0.0.1:8001/mcp`，在管理后台创建 MCP 访问令牌并选择 scope，再在客户端配置 `Authorization: Bearer <令牌>`。`MCP_PUBLIC_BASE_URL` 用于生成客户端可访问的链接；变更端口后必须同步修改。不要把令牌提交到 Git。

管理员在 Skills 广场搜索 GitHub Skill，或在 `GitHub skill sources` 添加固定公开来源。结果进入私有候选；在“候选审核”确认说明和用途后才发布。`Skill purposes` 管理用途层级，`Featured skills` 配置精选。没有可识别许可证的 GitHub 结果不能导入。

## 7. 停止、更新与备份

在启动终端按 `Ctrl+C` 停止网页。**自动启动的后台文献 worker 会继续运行**：按启动输出的 PID 在任务管理器核对后停止，或前台单独运行 worker 以便用 Ctrl+C 结束。不要停止不属于本项目的 Python 进程。更改模型/token 配置后，网页和后台 worker 都需重启。

Worker PID 与日志默认在 `LOCAL_STORAGE_ROOT` 下：`worker.pid`、`worker.stdout.log`、`worker.stderr.log`。状态目录不可写时启动脚本会提示改用项目 `.runtime/`；它只是状态/日志回退，不会移动论文数据。

更新代码前停止服务并保存本地改动；正常快进更新后执行：

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\start.ps1
```

保存账号/元数据与业务记录的 `db.sqlite3`、完整 `LOCAL_STORAGE_ROOT` 目录和 `.env`，应在停止网页及 worker 后一起备份。`.env` 中的密钥还用于已保存凭据的解密，不能随意更换。所有 PDF/解析产物、数据库、密钥、运行日志和截图均留在本机忽略目录，不上传仓库。

## 8. 常见问题与验证

| 现象 | 排查步骤 |
| --- | --- |
| 启动找不到 Python/Uvicorn | 确认在仓库根目录创建 .venv 并安装 requirements.txt；不要调用系统环境的 uvicorn |
| 数据目录/PID 拒绝访问 | LOCAL_STORAGE_ROOT 改成有写权限的目录；日志回退位置看启动输出；不要删除论文目录 |
| 8001 被占用 | 关闭旧的本项目网页进程，或 `start.ps1 -Port 8010`；同步 MCP_PUBLIC_BASE_URL |
| 修改页面后仍显示旧界面 | 重启网页后刷新；必要时 Ctrl+Shift+R |
| 上传已完成但解析排队 | 配置 MINERU_API_TOKEN，确认 worker 运行；使用 plab literature status 查询 |
| Parse 已存在但 Overview 失败 | 检查 PAPER/DeepSeek 配置及错误阶段；PDF/原文应仍可读，不必删除原论文 |
| invalid_configuration | PAPER base/Chat/Overview 模型同时填全；注意已有 shell 环境变量优先于 .env |
| http_401 / http_403 | 代理 key、账号权限或模型权限不正确；在代理管理界面检查，不公开 key |
| transport_error | 确认代理正在运行、端口与 API 根正确；检查代理日志、单次超时和模型速度，客户端等待期间有耗时提示 |
| invalid_output / empty_analysis / truncated | 输出没满足 JSON/引用约束、无有效结论或超出输出预算；换实际可用模型或有界调整 MAX_TOKENS 后重试 |
| degraded / evidence-fallback | 这是模型失败后的原文证据摘录，不应当作完整科研理解结果；可核对证据并重新生成 |
| Chat busy / 409 | 前轮仍在运行，等待历史刷新；过期 pending 会释放。不要连续多次提交同一问题 |
| 图像无法读取 | 当前 parse 可能无 raw 图片或资产缺失；用“查看 PDF 对应页”，PyPDF 不会补造图片 |
| 没有 AI 标签 | 列表来自当前可用 parse 的 Overview topics；没有生成 Overview 时不会用书目元数据标签假装补齐 |

网页请求/AI 脱敏错误在启动终端；worker 日志在上述目录。Skeleton 运行记录保存于 `PaperAnalysisRun`（状态、error_code、时间和上下文清单），Chat 保存在 conversation/message 表。原始模型输出和论文资料不要复制到公开 issue。

常规验证命令：

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --check
.\.venv\Scripts\python.exe manage.py test --noinput
openspec.cmd validate --all --strict --no-interactive
```

OpenSpec CLI 是开发文档校验工具，基础运行不需要安装。真实接口、完整论文语义和浏览器行为需另外验收；mock 测试通过不等于模型结论必然正确。

本仓库使用 [AGENTS.md](AGENTS.md) 的维护约定。设计与验证记录位于 [docs/decisions](docs/decisions/) 和 [docs/preparation](docs/preparation/)，正式/待实施规范位于 [openspec](openspec/)。对外部署需关闭 `DJANGO_DEBUG`，设置真实 `ALLOWED_HOSTS`，并配置 TLS、令牌和访问控制；本机启动示例不代表生产部署方案。
