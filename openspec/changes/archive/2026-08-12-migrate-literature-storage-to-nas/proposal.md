## Why

当前文献上传、预览和 MCP 下载直接依赖 NJU Box 专用 API，无法将新文献写入组内 NAS，也无法在同一数据库中明确区分不同文件后端。现在需要把新文献的对象存储切换到 NAS WebDAV，同时保留 NJU Box 文献适配器作为显式可选的旧后端。

## What Changes

- 新增统一的文献对象存储接口，覆盖上传、流式读取、删除和可下载地址生成所需能力。
- 新增 NAS WebDAV 文献存储适配器，默认写入配置的 `Literature/` 根目录，且不向客户端暴露 NAS 凭据。
- 按当前部署决定，NAS WebDAV 连接继续使用 HTTPS 加密，但固定跳过服务器证书链和主机名验证。
- 为文献上传记录持久化 `storage_backend`，新记录默认使用 NAS；既有记录保持 NJU Box 归属，不自动迁移或删除。
- 网页上传、内嵌 PDF、管理员删除、MCP 上传与下载统一按记录选择存储后端。
- 保留 NJU Box 文献适配器，可通过显式配置重新设为新文献后端；默认不再用于新文献上传。
- 继续保持上传成功后元数据解析失败不回滚文件，以及未发布文献不进入 MCP 文献上下文的现有行为。
- Shared Skills 的 NJU Box 上传与下载不在本次变更范围内。

## Capabilities

### New Capabilities

- `literature-object-storage`: 定义文献对象按后端上传、读取、删除、下载和配置选择的行为，以及 NAS WebDAV 与旧 NJU Box 的兼容边界。

### Modified Capabilities

- 无。

## Impact

- 影响 `apps/box_upload` 的模型、服务、网页上传、PDF 流式响应、管理员删除与测试。
- 影响 `apps/mcp_gateway` 的文献上传和文献下载接口；Skills MCP 行为保持不变。
- 新增一项 Django 数据库迁移，为既有上传记录回填 NJU Box 后端标识。
- 使用本地环境变量读取 NAS WebDAV 地址、账号、密码和 `Literature/` 根目录；真实凭据不进入源码、示例配置或版本控制。
- 依赖 NAS WebDAV 的 HTTPS 可达性和服务账号权限；接受跳过服务器身份验证带来的中间人攻击风险，不迁移或删除现有 NJU Box 测试文件。
