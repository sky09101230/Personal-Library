# PostgreSQL 迁移准备

## 已完成的人工准备

- PostgreSQL 18.4 已安装为自动启动的 Windows 服务 `postgresql-x64-18`。
- 服务仅监听 `127.0.0.1:5432` 和 `::1:5432`，不接受局域网或互联网连接。
- 数据库 `agentsys` 已创建，所有者为可登录但非超级用户的 `agentsys_app`。
- `agentsys_app` 已实际连接并确认 `current_database=agentsys`、`current_user=agentsys_app`。
- 本机 `.env` 已配置 `AGENTSYS_DB_ENGINE`、`AGENTSYS_DB_NAME`、`AGENTSYS_DB_USER`、`AGENTSYS_DB_PASSWORD`、`AGENTSYS_DB_HOST` 和 `AGENTSYS_DB_PORT`。
- `.env`、SQLite 数据库及冲突副本已加入 `.stignore`；两台机器迁移期间保持 AgentSys 同步暂停。

## 切换前条件

- Uvicorn 必须停止，8000 端口不得监听。
- SQLite 必须通过 `PRAGMA quick_check` 与外键检查，并在同步目录外保留副本。
- PostgreSQL 目标必须没有应用表或业务记录。
- 临时夹具和核对证据必须位于仓库与 Syncthing 目录之外，并按凭据级敏感数据保护。

## 验证合同

- PostgreSQL 无待执行 migration。
- 应用自有表的记录数、主键和关系与冻结 SQLite 证据一致。
- PostgreSQL 专用夹具记录所有 NUL 规范化位置与数量，除此之外序列化字段保持一致。
- fresh migration taxonomy 在无 Skill/Candidate 引用时由冻结夹具替换，以保留 SQLite 分类主键。
- `contenttypes` 与权限由当前 migrations 生成，不把 SQLite 副本视为权威。
- 数据库序列的下一值高于已迁移主键。
- 现有用户认证、首页、MCP Token、文献上传者与发布状态、NAS Skill 发布记录均可查询。
- `pg_dump` 自定义格式备份能够被 `pg_restore --list` 读取。

## 运行边界

迁移和验证完成前不启动 Uvicorn，不恢复 Syncthing。任何验证失败都先停止并保留两端证据，不删除 SQLite 来源、不清空 NAS 对象，也不把部分 PostgreSQL 数据反写 SQLite。

## 2026-08-12 迁移结果

- 冻结 SQLite：24 张表、415 行，`quick_check=ok`、外键违规 0，工作副本与冻结副本 SHA-256 一致。
- 数据转换：仅 3 条 `CanonicalDocument.metadata_evidence` 中 4 个嵌套字符串的 13 个 NUL 替换为空格；转换位置和数量单独留证。
- PostgreSQL：所有 migrations 已应用，应用表数量与 SQLite 一致，264 个 Django 对象回读后与 PostgreSQL 专用夹具深度相等，22 个自增序列均高于现有主键，无未验证外键。
- 运行路径：迁移后的现有 Session 首页返回 200；MCP Token 查询命中原 owner 与 3 个 scopes 且验证事务回滚；重复 DOI 文献保留上传 `94/99` 与 uploader `2`；NeurIPS 文献保留上传 `103` 与提案 `29`；20 个 Skill 发布记录均为 NAS 后端。
- 自动验证：数据库配置回归测试 1 个、完整 Django 测试 169 个全部通过；15 个 OpenSpec change 严格校验通过；`makemigrations --check --dry-run` 无变化。
- 备份：自定义格式 PostgreSQL dump 已生成，`pg_restore --list` 可读取 216 个目录项；冻结 SQLite 继续保留。
- 实服务：Uvicorn 使用本机 `.env` 启动，根路径 302、登录页 200、未认证 MCP 401。

未执行真实 NAS PDF/Skill 下载、真实 Zotero API 或 DeepSeek 请求，也未把 PostgreSQL dump 恢复到第二个临时数据库；这些不属于本次数据库内容迁移的必要写入验证。
