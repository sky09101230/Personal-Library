## PLAB Scientific Agent

Local development:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set AGENTSYS_DB_ENGINE=sqlite in .env for local development.
python manage.py runserver
```

Configure the local `.env` before uploading. See `docs/preparation/02-Django-NJU-Box-API.md`.

当前部署使用 PostgreSQL 保存业务数据，文献和 Skill 新文件默认写入 NAS WebDAV。SQLite、Django `runserver` 和 NJU Box 仅用于本地开发或读取历史记录。网页与 `/mcp` 由同一个 ASGI 应用提供；生产环境应让 Uvicorn 只监听 `127.0.0.1:8000`，再由反向代理提供 TLS。

### 管理员

在项目目录执行以下命令创建管理员账号：

```powershell
python manage.py createsuperuser
```

按提示输入用户名、邮箱和密码。创建后访问 `http://127.0.0.1:8000/admin/`。

在 `GitHub skill sources` 中添加或管理 Skills 来源（名称、仓库地址、可选分支和启用状态）。回到 `/skills/` 后，管理员点击“扫描到候选池”；扫描只更新私有候选，不会直接出现在正式 Skills 广场或 MCP 中。管理员在“候选审核”中确认内容、用途和说明后，才能批准并发布正式版本。

在 `Skill purposes` 中先添加大用途，再添加父级为该大用途的小用途；随后在 `Shared skills` 中为每个 Skill 选择小用途。要发布管理员精选，在 `Featured skills` 中选择一个 Skill、填写一句推荐语并设置排序值。

在 `Uploaded documents` 页面选择记录，使用 `Delete selected files from object storage and database` 动作。系统根据每条记录的 `storage_backend` 删除 NAS WebDAV 或历史 NJU Box 文件，远端删除成功后才删除数据库记录；普通用户不会看到该管理入口。
