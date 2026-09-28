## PLAB Scientific Agent

本机开发（无需 NAS 或 PostgreSQL）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 在 .env 中设置随机 DJANGO_SECRET_KEY。
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\start.ps1
```

打开 http://127.0.0.1:8001/。执行 `.\start.ps1` 会启动网页，并在检测到 `MINERU_API_TOKEN` 且单 worker 未运行时自动启动文献处理 worker；没有 token 时只启动网页并显示提示。worker 的 PID 保存在 `E:\Personal-Library\data\worker.pid`，输出写入 `E:\Personal-Library\data\worker.stdout.log` 和 `E:\Personal-Library\data\worker.stderr.log`。

默认 `.env.example` 使用 SQLite 和本地文件存储：

- `db.sqlite3`：账号、文献元数据及业务记录。
- `E:\Personal-Library\data\literature\originals\`：原始文件；`E:\Personal-Library\data\literature\derived\parses\`：解析产物。
- `E:\Personal-Library\data\skills\`：正式 Skill；`E:\Personal-Library\data\skill_candidates\`：待审核候选。
- `LOCAL_STORAGE_ROOT`：可改为其他本地数据目录；相对路径仍以项目根目录为准。

这些运行数据和 `.env` 均被 Git 忽略。备份时停止服务并一起保存数据库、`E:\Personal-Library\data` 目录和 `.env`（其中的密钥也用于已保存凭据的解密）。

基础网页、上传和文件管理无需外部 API 密钥。按需在 `.env` 中启用：

| 功能 | 配置 |
| --- | --- |
| AI 元数据建议、文献概览、Skill 摘要 | `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`；模型需填写账号实际可用的名称 |
| MinerU 云端结构化解析 | `MINERU_API_TOKEN`；使用时会上传文献到外部解析服务 |
| 搜索 GitHub 公开 Skill | `GITHUB_API_TOKEN`，只授予读取公开资源所需权限 |
| Zotero 元数据 | 在应用的 Zotero 设置中连接；不影响本地启动 |
| Crossref 联系邮箱 | `CROSSREF_MAILTO`，可选 |

修改 `.env` 后重启。也可以手动启动后台文献解析/概览队列：

```powershell
.\.venv\Scripts\python.exe manage.py plab literature worker
```

新上传文献沿用原项目逻辑，自动加入 MinerU 队列；未配置密钥时先不启动 worker，文件管理仍可使用。本地 PyPDF 解析器不需要 MinerU token，可用 `manage.py plab literature enqueue --upload-id <ID> --parser pypdf` 手动入队，但 AI 概览仍需要 DeepSeek。MinerU 多通道 worker-pool 是原部署的可选能力，本机起步无需配置多组 token。

原项目的 PostgreSQL 和 NAS WebDAV 后端仍保留；已有部署可通过环境变量继续选择。个人本机使用不必部署 PostgreSQL，未来多人并发或服务器部署时再单独迁移数据。网页与 `/mcp` 由同一个 ASGI 应用提供；对外部署需关闭 DEBUG 并配置 TLS 和访问控制。

### 管理员

在项目目录执行以下命令创建管理员账号：

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

按提示输入用户名、邮箱和密码。创建后访问 `http://127.0.0.1:8001/admin/`。

管理员可在 Skills 广场点击“搜索 GitHub Skill”，按关键词查找公开仓库中的 `SKILL.md`；必须配置仅能读取公开资源的 `GITHUB_API_TOKEN`，没有 GitHub 可识别许可证的结果不能导入。也可以继续在 `GitHub skill sources` 中管理固定来源并扫描整个仓库。两种方式都只更新私有候选，不会直接出现在正式 Skills 广场或 MCP 中；管理员在“候选审核”中确认内容、用途和说明后，才能批准并发布正式版本。

在 `Skill purposes` 中先添加大用途，再添加父级为该大用途的小用途；随后在 `Shared skills` 中为每个 Skill 选择小用途。要发布管理员精选，在 `Featured skills` 中选择一个 Skill、填写一句推荐语并设置排序值。

在 `Uploaded documents` 页面选择记录，使用 `Delete selected files from object storage and database` 动作。系统根据每条记录的 `storage_backend` 删除本地或 NAS WebDAV 文件，文件删除成功后才删除数据库记录；普通用户不会看到该管理入口。历史 NJU Box 后端已停用。
