## PLAB Scientific Agent

Local development:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py runserver
```

Configure the local `.env` before uploading. See `docs/preparation/02-Django-NJU-Box-API.md`.

### 管理员

在项目目录执行以下命令创建管理员账号：

```powershell
python manage.py createsuperuser
```

按提示输入用户名、邮箱和密码。创建后访问 `http://127.0.0.1:8000/admin/`。

在 `GitHub skill sources` 中添加或管理 Skills 来源（名称、仓库地址、可选分支和启用状态）。来源仅用于同步和溯源；回到 `/skills/` 后由管理员点击 `Sync from GitHub` 同步启用的来源。同步会在后台运行，页面会显示当前来源、当前 Skill、上传数和跳过数。

在 `Skill purposes` 中先添加大用途，再添加父级为该大用途的小用途；随后在 `Shared skills` 中为每个 Skill 选择小用途。要发布管理员精选，在 `Featured skills` 中选择一个 Skill、填写一句推荐语并设置排序值。

在 `Uploaded documents` 页面选择记录，使用 `Delete selected files from NJU Box and database` 动作。系统会先删除 NJU Box 中的远端文件，成功后才删除本地数据库记录；普通用户不会看到该管理入口。
