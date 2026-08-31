# AgentSys 开发者说明书

本文面向维护 AgentSys 的开发者、部署人员和管理员。说明以当前代码为准；跨模块的长期设计决策仍以 `docs/decisions/` 为准，准备项和迁移证据以 `docs/preparation/` 为准。

## 1. 项目边界

AgentSys 是一个 Django 5.2 单体应用，同时提供网页和 `/mcp` Streamable HTTP MCP 服务：

- `apps/accounts`：邀请码注册、登录和登出。
- `apps/box_upload`：文献元数据、PDF 暂存确认、NAS 存储、文献库、下载、Zotero 和 metadata 审核。
- `apps/skills`：Skill 分类、投稿候选池、GitHub 发现/扫描、AI 摘要分类、发布、下载和学术推荐。
- `apps/mcp_gateway`：Bearer Token 验证、文献/Skill MCP 工具和短时下载链接。
- `config`：Django 设置、URL、ASGI/WSGI 入口。
- `templates`：网页模板；`staticfiles/` 是 `collectstatic` 的生成目录，不提交生成内容。
- `docs/decisions`：已确认的技术/治理决策；`docs/preparation`：准备与验收记录。

运行时数据的当前基线是 PostgreSQL；新文献 PDF、Skill 候选快照和正式 Skill 发布包默认使用 NAS WebDAV。SQLite 只用于本地开发、测试和迁移前快照。NJU Box 已退出当前运行路径，不要为新功能恢复该后端。

## 2. 开发环境

建议使用 Python 3.14，并显式使用项目解释器：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

本地开发最小配置：

```dotenv
DJANGO_SECRET_KEY=仅用于本地的随机值
DJANGO_DEBUG=true
AGENTSYS_DB_ENGINE=sqlite
ALLOWED_HOSTS=localhost,127.0.0.1
```

如果要验证真实文件流，另行配置 NAS WebDAV 的地址、账号和 Literature/Skills 根目录；不要把真实凭据写入仓库、测试夹具、文档或日志。`.env` 优先于源代码默认值，修改后必须重启进程。

初始化数据库并启动网页：

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

开发服务器适合本机调试，不得作为生产公网入口。网页和 MCP 的统一 ASGI 入口是 `config.asgi:application`。

## 3. 配置与依赖

依赖版本在 `requirements.txt` 固定。关键配置如下：

| 配置 | 作用 |
| --- | --- |
| `AGENTSYS_DB_ENGINE` | `sqlite` 或 `postgresql`；生产使用 PostgreSQL |
| `AGENTSYS_DB_*` | PostgreSQL 数据库名、用户、密码、地址和端口 |
| `NAS_WEBDAV_*` | NAS 地址、服务账号、文献/Skill/候选根目录 |
| `MCP_PUBLIC_BASE_URL` | MCP 对外 HTTPS 基地址；必须与反向代理 Host 一致 |
| `MCP_MAX_UPLOAD_BYTES` | 网页/MCP/Zotero PDF 统一上限，示例为 100 MiB |
| `LITERATURE_DOWNLOAD_LINK_MAX_AGE` / `SKILL_DOWNLOAD_LINK_MAX_AGE` | 短时下载链接有效期，默认 300 秒 |
| `DOI_RESOLVER_URL` / `CROSSREF_API_URL` / `METADATA_HTTP_TIMEOUT` | 文献 DOI/BibTeX/Crossref 解析 |
| `ZOTERO_API_URL` | Zotero Web API 地址；用户 API Key 加密存库，不写环境变量 |
| `GITHUB_API_TOKEN` | 仅用于管理员发现公开 GitHub Skill，不能授予私有仓库权限 |
| `DEEPSEEK_API_KEY` 等 | metadata/Skill 摘要与分类的服务端 AI 配置 |

上传流程会先校验 PDF 签名、计算 SHA-256、提取有限证据，再写 NAS。DOI/BibTeX 预检失败时，新批次在写存储前停止；后续 AI metadata 失败不删除已经确认入库的 PDF。

## 4. 数据和代码维护边界

### 文献

`CanonicalDocument` 是文献身份和元数据；`UploadedDocument` 是具体 PDF 附件、上传者、摘要、存储后端和文件角色。文献身份优先使用入口已确认的 Zotero 外部引用，其次是标准化 DOI，再其次是 SHA-256；不要按标题或文件名猜测合并。

网页上传先创建 `UploadReviewBatch`/`UploadReviewItem` 私有暂存。上传者确认标题和 DOI 后，单个事务才创建或关联正式记录；缺少标题会阻断整批确认，缺少期刊只是警告。已有已验证 metadata 不会被重复确认覆盖。成功保存正文 PDF 的正式文献设为 `published`，没有 PDF 的 Zotero-only 记录仍是待处理状态。

`index_status=published` 是网页公开检索和 MCP 文献上下文的边界；`metadata_status` 只表示 metadata 完整性，不等同于发布状态。删除必须先删除远端对象，成功后再删除数据库记录；失败时保留记录以便恢复。

### Skills

普通 ZIP 投稿和 GitHub 扫描都先进入 `SkillCandidate` 私有候选池。候选校验包括单个 `SKILL.md`、路径穿越、符号链接、加密成员、禁止资产、大小和解压体积等；候选内容不得执行。只有管理员审核说明、用途和校验结果后，`publish_candidate` 才会复制快照、写入 NAS、创建正式 `SharedSkill`/`SharedSkillRelease`。

DeepSeek 摘要/分类是独立后台流程，只更新数据库，不初始化或读取 NAS 发布包。人工设置的 `purpose_is_manual` 和 `description_is_manual` 必须继续保护人工决定。正式 Skill 下载优先取 NAS 发布包；短时链接过期或存储失败应返回可诊断错误。

### MCP

`config.asgi` 将 `/mcp` 路由到 `apps.mcp_gateway.server`，普通 URL 仍由 Django 处理。访问令牌只保存摘要，支持过期、停用和 scope：`literature:read`、`literature:write`、`skills:read`。新增工具时必须同时更新 scope 校验、发布边界、错误信息和 MCP 测试；不要在响应中暴露 NAS 凭据或内部远端路径。

## 5. 测试、检查和迁移

常规检查：

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 1
```

本地 SQLite 测试（当 PostgreSQL 角色没有 `CREATEDB` 时）：

```powershell
$env:AGENTSYS_DB_ENGINE = "sqlite"
python manage.py test --verbosity 1
```

按风险补充聚焦测试：

- PDF、重复 DOI、元数据和删除：`apps/box_upload/tests.py`、`test_upload_review.py`、`test_metadata_resilience.py`、`test_storage.py`。
- Zotero 和下载流：`apps/box_upload/tests.py` 中对应 `ZoteroImportTests`、下载测试。
- Skill 候选、发布、GitHub 搜索、AI 分类和后台任务：`apps/skills/test_candidates.py`、`test_github_search.py`、`test_academic_recommendations.py`、`tests.py`。
- MCP 认证、scope、发布文献和 Skill 工具：`apps/mcp_gateway/tests.py`。
- 邀请码注册：`apps/accounts/tests.py`。

修改模型后先生成并审阅迁移：

```powershell
python manage.py makemigrations
python manage.py migrate
```

迁移生产 PostgreSQL 前停止 Uvicorn 和同步服务，保留 SQLite 冻结副本；核对 migration、记录数、主键/外键、唯一约束、序列、用户认证、MCP Token、文献发布关系和 NAS Skill 发布记录。PostgreSQL 接受正常写入后，不得通过切换旧 SQLite 文件回滚，应从 PostgreSQL 备份恢复或做显式对账。

## 6. 后台任务

网页请求只负责创建数据库任务并启动独立进程；同一时间最多一个活动 Skill 任务。常用命令：

```powershell
python manage.py queue_metadata_proposals --limit 100 --requested-by <staff_username>
python manage.py run_metadata_worker --once
python manage.py run_metadata_worker --poll-interval 2
python manage.py scan_skill_candidates_job <job_id> [--source-id <id>]
python manage.py enrich_skills_job <job_id> [--source-id <id>]
python manage.py refresh_academic_skill_recommendations_job <job_id>
```

后台任务失败时先查看 Django 日志、`SkillSyncJob.error`/heartbeat 和 `MetadataProposal` 状态；确认没有旧的 `queued/running` 任务后再重试。不要直接删除运行中的候选、暂存批次或 NAS 文件来“清理”状态。`migrate_skill_archives_to_nas` 已废弃，执行应明确报错。

## 7. 部署与运维

生产启动顺序：配置 `.env`、确认 PostgreSQL/NAS 可用、执行迁移和 `collectstatic`，再启动 Uvicorn：

```powershell
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

完成迁移和静态文件收集后，也可以在仓库根目录使用启动脚本；脚本先执行 Django 系统检查，再以前台进程启动 Uvicorn，按 `Ctrl+C` 停止：

```powershell
.\start.ps1
# 仅在明确需要局域网直连时：
.\start.ps1 -BindAddress 0.0.0.0 -Port 8000
```

脚本不会自动执行迁移或 `collectstatic`，避免普通重启隐式修改数据库或生成文件。

反向代理负责 TLS，并将正确的 `Host`、`Authorization` 和请求体转给 Uvicorn；8000 只监听本机。`ALLOWED_HOSTS`、`MCP_PUBLIC_BASE_URL`、证书域名和代理 Host 必须一致。首次部署后验证：登录页 200、首页可访问、未认证 `/mcp` 返回 401、有效 Token 能列出已发布文献/Skill、短时下载链接能读取有效文件。

日常维护检查：数据库备份可恢复；NAS Literature/Skills 根目录权限仍是最小范围；令牌按人员撤销或轮换；没有把真实资料、数据库备份、向量索引、模型权重或密钥加入 Git；任务失败和暂存批次有可追踪记录；部署前运行完整测试和 `openspec validate --all --strict --no-interactive`（命令不可用时按仓库 OpenSpec 指南处理）。

## 8. 变更流程

1. 先在 `docs/decisions/` 或 `docs/preparation/` 记录新的技术边界和验收条件。
2. 读取相关模型、服务、视图、模板和测试；保持网页与 MCP 共用的 ingestion/storage 逻辑。
3. 用最小改动实现，并为状态、权限、失败清理和重复路径补测试。
4. 运行聚焦测试、完整测试、`check` 和迁移检查；记录未验证的真实 NAS/Zotero/AI 外部联调。
5. 提交只包含一个目的的变更，提交信息使用 `feat:`、`fix:`、`docs:`、`test:` 或 `chore:` 前缀。

## 9. 排障速查

| 现象 | 先检查 |
| --- | --- |
| 连接数据库失败 | `.env` 有效值、`AGENTSYS_DB_ENGINE`、PostgreSQL 服务/权限和端口 |
| PDF 上传 413 | `MCP_MAX_UPLOAD_BYTES`、反向代理请求体上限和进程是否已重启 |
| NAS 读写失败 | `NAS_WEBDAV_BASE_URL`、账号权限、根目录、HTTPS 证书和存储后端；不要只删数据库记录 |
| 文献不出现在 MCP | 是否有有效正文 PDF，以及 `index_status=published`；metadata 未验证不必然阻止发布 |
| AI 建议没有结果 | `DEEPSEEK_API_KEY`、任务状态、超时/错误字段；可保留原始解析 metadata 并稍后重试 |
| Skill 扫描不发布 | 候选是否仍为 pending、许可证/压缩包校验是否通过、是否完成管理员审核；扫描本来不会直接发布 |
| MCP 返回 401/403 | Bearer Token 是否有效、未过期/启用、scope 是否包含目标工具，Host 是否与 `MCP_PUBLIC_BASE_URL` 一致 |
