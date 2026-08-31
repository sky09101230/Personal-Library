## Context

当前 `UploadedDocument.remote_path` 只保存远端路径，所有文献调用方都假定该路径属于 NJU Box。网页上传、内嵌 PDF、管理员删除、后台元数据任务和 MCP 文献工具分别直接调用 NJU Box 函数，因此仅替换一个 URL 无法接入采用 Basic Auth WebDAV 的 Synology NAS。

NAS 已提供 HTTPS WebDAV 服务，文献目录映射为 `/public/PLAB_KnowledgeBase/Literature/`。真实凭据保存在本机、Git 忽略的 `.env` 中。既有 NJU Box 内容均为测试数据，本次不要求复制；但旧适配器和旧记录归属必须保留，以便显式恢复或按需迁移。

## Goals / Non-Goals

**Goals:**

- 新文献默认通过 NAS WebDAV 写入配置的 `Literature/` 根目录。
- 每条文献上传记录明确保存其对象存储后端，并按记录完成读取和删除。
- 网页与 MCP 下载均不暴露 NAS 账号、密码或带凭据的 URL。
- 保留 NJU Box 文献适配器，可通过配置显式重新选择。
- 保持元数据解析、发布状态、PDF Range 转发和管理员删除失败保护等现有业务边界。

**Non-Goals:**

- 不复制、删除或批量改写现有 NJU Box 测试文件。
- 不迁移 SQLite，不部署 PostgreSQL，也不改变 `5090` 主机运行方式。
- 不迁移 Shared Skills 的 NJU Box 发布包。
- 不预建推导、代码、数据等尚未落地的对象模型或 NAS 目录。

## Decisions

### 1. 新增小型文献存储适配层，保留 NJU Box 实现

新增统一接口，提供 `upload`、`open_stream` 和 `delete` 三项文献所需能力。NAS 适配器实现 WebDAV；NJU Box 适配器只包装现有函数。应用层捕获统一的 `LiteratureStorageError`，而 `NjuBoxUploadError` 继续作为其子类供 Skills 和旧测试使用。

选择它而不是重写 `services.py`，因为 Skills 仍依赖 NJU Box 的仓库解锁、临时链接和上传协议；本次变更不应扩大到 Skills。

### 2. 记录级后端路由，配置只决定新上传

`UploadedDocument` 新增 `storage_backend`，既有行回填为 `nju_box`。网页或 MCP 新上传时读取 `LITERATURE_STORAGE_BACKEND`，缺省值为 `nas_webdav`，并把实际后端与远端路径一起写入数据库。

读取和删除始终使用记录的 `storage_backend`，不在运行时尝试另一个后端。这样不会把 NAS 权限、网络或文件缺失错误伪装成回退成功，也不会在两个后端间误取同名对象。

### 3. NAS 路径按上传隔离，不覆盖同名文件

NAS 适配器在 `NAS_WEBDAV_LITERATURE_ROOT` 下为每次上传生成随机对象名，并保留经过清理的原始扩展名。远端路径只保存 WebDAV 共享根内的绝对路径；适配器拒绝非绝对根路径和包含父目录跳转的配置。

选择独立对象名而不是内容哈希共用文件，是为了保持当前“一条上传记录对应一个可独立删除的远端对象”语义，避免删除一个重复上传记录时破坏另一个记录。

### 4. 使用标准库实现 WebDAV，并固定跳过服务器证书验证

适配器使用 `http.client.HTTPSConnection`、`ssl._create_unverified_context()` 和 Basic Authorization，实现 `PUT`、带可选 Range 的 `GET`、`DELETE`。上传按 Django `UploadedFile.chunks()` 流式发送，不引入新 HTTP 依赖，也不在内存复制整份网页上传文件。

按用户明确决定，NAS WebDAV 的生产请求固定跳过证书链和主机名验证，不增加配置开关，也不影响 NJU Box 或其他 HTTPS 客户端。TLS 仍加密传输，但应用无法确认连接对象确为目标 NAS。

### 5. 下载统一由 PLAB 应用代理

登录用户的下载和内嵌 PDF 都由 Django 从记录对应后端打开流，再以 `StreamingHttpResponse` 返回。MCP 的 `get_literature_download_link` 返回由 Django 签名、带有效期的 PLAB 下载 URL；公开下载端点验证签名、有效期和 `index_status=published` 后才代理文件。

这替代 NAS 无法安全提供的匿名临时链接，同时避免向客户端暴露管理员凭据。Skills 的 NJU Box 临时下载链接保持原行为。

### 6. 上传成功与元数据处理继续解耦

远端上传成功后先在事务内写入 `UploadedDocument`，随后执行现有元数据解析与异步提案逻辑。元数据失败不得删除已写入 NAS 的对象或上传记录，保持现有契约。

## Risks / Trade-offs

- [跳过证书验证会允许中间人伪装 NAS 并获取 Basic Auth 凭据或篡改文献] → 将例外严格限制在 NAS WebDAV 适配器；风险由用户明确接受，后续配置可信证书时应恢复严格校验。
- [应用代理增加 `5090` 的网络流量] → 保留流式传输和 Range 请求，不缓冲整份 PDF；后续如容量证明需要再引入反向代理或受控下载网关。
- [管理员账号权限过大] → 先按用户明确要求读取现有管理员配置，后续换成仅限 `Literature/` 的服务账号无需改代码。
- [远端文件上传成功但数据库事务失败会留下孤儿对象] → 上传失败不写记录；数据库失败时尽力删除刚上传对象并记录原始错误，删除失败不掩盖数据库失败。
- [旧记录默认值错误会导致从 NAS 查找 NJU Box 路径] → 数据迁移明确把所有既有记录回填为 `nju_box`，新上传代码总是显式写入实际后端。

## Migration Plan

1. 部署模型迁移，为既有 `UploadedDocument` 行回填 `nju_box`。
2. 在 `5090` 的本地环境配置 NAS WebDAV 参数；保持 NJU Box 参数不删除。
3. 从 `5090` 执行测试对象 PUT/GET/DELETE 冒烟检查，并确认只有 NAS WebDAV 连接跳过证书校验。
4. 将 `LITERATURE_STORAGE_BACKEND` 设为或保持默认 `nas_webdav`，运行 Django 检查与回归测试后重启服务。
5. 上传一份唯一测试 PDF，验证数据库后端标识、NAS 路径、网页 Range 预览、MCP 发布门禁和删除保护。

回滚时把 `LITERATURE_STORAGE_BACKEND` 显式设为 `nju_box` 并重启服务；已经写入 NAS 的记录仍按自身后端读取，不需要复制或改写。数据库迁移与新字段保留，不做破坏性回滚。

## Open Questions

- 无。
