# 0027 PostgreSQL 权威数据库

## 决策

AgentSys 的运行时关系数据迁移到与 Django/Uvicorn 同机的 PostgreSQL，当前部署使用 `agentsys` 数据库和非超级用户 `agentsys_app`，仅通过 `127.0.0.1:5432` 连接。PostgreSQL 是迁移后的唯一权威数据源；SQLite 仅保留为冻结的迁移来源、开发后端和切换前回滚依据，不再作为两台机器之间的数据同步机制。

数据库后端由本机环境变量显式选择。PostgreSQL 密码只存放在 Git 与 Syncthing 均忽略的 `.env`，不得写入代码、文档、OpenSpec、日志或命令参数。PostgreSQL 数据目录、SQLite 文件、迁移夹具和数据库备份均不得进入 Git 或 Syncthing。

## 迁移边界

- 迁移前停止 Uvicorn 并冻结已恢复的 `db.sqlite3`。
- 由 Django migrations 在空 PostgreSQL 数据库创建结构。
- 使用 Django 原生序列化迁移应用数据并保留主键；`contenttypes` 与 `auth.permission` 由 migrations 重新生成。
- SQLite 派生元数据 JSON 中 PostgreSQL 不支持的 NUL 控制字符仅在 PostgreSQL 专用夹具中替换为空格，并记录模型、主键、字段和数量；冻结 SQLite、原夹具和原始 PDF 不变。
- 空库 migration 生成的 Skill 用途分类若因历史预置记录而与 SQLite 主键不同，则只在确认无引用后清除新种子，并由夹具恢复 SQLite 的 29 条原主键分类。
- 在恢复写入前核对逐表数量、主键、外键关系、唯一约束、序列、登录、首页、MCP Token、文献发布关系和 NAS Skill 发布记录。
- 验证通过后创建 PostgreSQL 自定义格式备份；验证失败时停止，不向 SQLite 和 PostgreSQL 双写或尝试自动合并。

## 回滚

在 PostgreSQL 尚未接受正常业务写入前，可以停止 Uvicorn、将 `AGENTSYS_DB_ENGINE` 临时切回 `sqlite` 并使用未变更的 SQLite 来源。PostgreSQL 接受正常写入后，不得通过切换旧 SQLite 文件回滚；必须从 PostgreSQL 备份恢复或做显式数据对账。

## 不采用的方案

- 不同步 SQLite 或 PostgreSQL 数据目录，因为文件同步不提供数据库事务合并。
- 不引入 pgLoader，Django 原生 migrations 与序列化已经覆盖当前一次性迁移。
- 不引入连接池、远程数据库访问或高可用集群；当前只有一个同机应用实例。
