# 本地文件存储与 SQLite 开发环境

个人知识库首期在单台 Windows 电脑运行，使用 SQLite 保存业务数据，在 `E:\Personal-Library\data\` 下保存文件，无需 NAS 或 PostgreSQL 服务。

本地后端复用现有存储接口，文献原件放在 `literature/originals`，解析结果放在 `literature/derived/parses`；正式 Skill 与待审核候选使用独立目录。路径必须限制在各自根目录中，写入和移动不得覆盖已有文件。文件通过现有鉴权/签名下载入口读取，不公开整个 data 目录。

保留 NAS 后端兼容性，使用 LITERATURE_STORAGE_BACKEND=local 选择本地存储；LOCAL_STORAGE_ROOT 可指定数据目录。数据库中的 local 后端值用于读取已存文件。候选记录沿用原项目设计，切换部署存储前需先处理未审核候选。

启动脚本使用项目虚拟环境，仅绑定 127.0.0.1。数据库、原始资料、密钥及生成产物均不提交 Git。备份时应停止服务并同时备份 db.sqlite3、data 和 .env。
