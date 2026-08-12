# 0016 Skill 发布包迁移至 NAS WebDAV

## 决策

Skill 元数据继续保留在 PostgreSQL 业务数据库；ZIP 发布包迁移到 NAS 的 `/public/PLAB_KnowledgeBase/Skills`，与 `Literature` 同级。`SharedSkillRelease.storage_backend` 记录每个 ZIP 的实际后端，新发布默认写入 `nas_webdav`，旧记录初始标记为 `nju_box`。

网页和 MCP 下载均由 PLAB 服务端代理。MCP 返回短时签名链接，NAS 用户名和密码不会出现在客户端响应中。

## 理由

后端属于单条发布记录，迁移期间必须允许 NAS 与 NJU Box 共存。逐条路由可避免一次全局切换让未迁移 ZIP 失效；对象存储迁移不改变 PostgreSQL 中的业务记录。

## 迁移约束

- 目标 NAS PUT 成功前不得更新发布记录。
- 下载的旧文件必须通过归档大小和 ZIP 完整性检查。
- NJU Box 不可连接时，可按发布记录中的 Git 提交和 Skill 路径重建等价 ZIP，并校验 ZIP 完整性。
- 不覆盖或删除 NJU Box 原文件。
- 失败记录保留原后端、仓库 ID 和远程路径，可重复执行迁移命令。
- 继续沿用 0014 中用户明确接受的 NAS TLS 证书校验例外；该风险未在本次迁移中扩大为新的认证方式。
