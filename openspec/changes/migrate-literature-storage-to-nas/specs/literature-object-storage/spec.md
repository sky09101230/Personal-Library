## ADDED Requirements

### Requirement: 新文献使用配置的对象存储后端
系统 MUST 通过统一文献存储接口上传新文献，并将实际使用的后端标识与远端路径共同保存。缺少显式配置时，新文献后端必须为 `nas_webdav`。

#### Scenario: 网页上传新文献到 NAS
- **WHEN** 已登录用户通过网页上传有效 PDF，且未显式选择其他文献后端
- **THEN** 系统必须将对象写入 NAS `Literature/` 根目录，并将上传记录的后端保存为 `nas_webdav`

#### Scenario: MCP 上传新文献到 NAS
- **WHEN** 具有 `literature:write` 权限的 MCP 客户端上传有效 PDF
- **THEN** 系统必须使用与网页上传相同的默认存储选择，并保存实际后端和远端路径

### Requirement: NAS WebDAV 适配器保护凭据和路径
NAS WebDAV 适配器 MUST 通过跳过服务器证书链和主机名验证的 HTTPS 与服务端 Basic Authorization 执行对象操作，必须拒绝不安全或越界的根路径，且不得向网页或 MCP 响应暴露 NAS 凭据。该证书验证例外不得影响 NJU Box 或其他 HTTPS 客户端。

#### Scenario: NAS 使用不受信任且名称不匹配的证书
- **WHEN** NAS WebDAV 返回的证书链不受系统信任，或证书主机名与配置地址不匹配
- **THEN** NAS WebDAV 适配器必须继续建立加密连接并执行请求，且其他 HTTPS 客户端的证书验证行为保持不变

#### Scenario: 上传对象
- **WHEN** 适配器收到一个有效 PDF 上传对象
- **THEN** 适配器必须以不会覆盖同名既有对象的路径在配置的 `Literature/` 根目录执行 WebDAV PUT，并返回持久化远端路径

#### Scenario: 配置缺失
- **WHEN** NAS 地址、用户名、密码或文献根目录缺失或不合法
- **THEN** 系统必须在访问 NAS 前返回受控的文献存储配置错误

#### Scenario: 路径编码
- **WHEN** 远端路径包含空格、中文或其他需要 URL 编码的字符
- **THEN** WebDAV 请求必须对各路径段正确编码，且持久化路径保持可逆

### Requirement: 文献读取和删除按记录后端路由
系统 MUST 根据 `UploadedDocument.storage_backend` 选择读取和删除适配器，不得因某一后端失败而隐式尝试另一后端。

#### Scenario: 读取 NAS 文献
- **WHEN** 一个 NAS 文献记录被在线打开或下载
- **THEN** 系统必须从其 NAS 路径流式读取，并保留合法单区间 Range 请求及响应头

#### Scenario: 读取旧 NJU Box 文献
- **WHEN** 一个后端标识为 `nju_box` 的旧文献记录被读取
- **THEN** 系统必须调用保留的 NJU Box 文献适配器，而不访问 NAS

#### Scenario: 删除失败保护数据库记录
- **WHEN** 管理员删除文献，但对应后端无法删除远端对象
- **THEN** 系统必须保留数据库上传记录并显示受控错误

### Requirement: NJU Box 文献适配器保留但不作为默认后端
系统 MUST 保留 NJU Box 文献适配器以读取旧记录和支持显式回滚，但不得在缺省配置下将新文献写入 NJU Box。

#### Scenario: 缺省后端选择
- **WHEN** `LITERATURE_STORAGE_BACKEND` 未设置
- **THEN** 系统必须选择 `nas_webdav`

#### Scenario: 显式回滚新上传后端
- **WHEN** 运维人员将 `LITERATURE_STORAGE_BACKEND` 显式配置为 `nju_box` 并重启服务
- **THEN** 后续新文献必须使用 NJU Box，既有 NAS 记录仍必须从 NAS 读取

### Requirement: PLAB 代理文献下载
系统 MUST 由 PLAB 服务代理 NAS 文献内容，浏览器下载需要登录；MCP 下载链接必须短期有效、不可伪造，并在取文件时再次验证文献已发布。

#### Scenario: 登录用户下载
- **WHEN** 已登录用户请求一个可用文献上传记录
- **THEN** 系统必须流式返回对应后端内容和附件文件名，不要求用户输入 NAS 或 NJU Box 凭据

#### Scenario: MCP 获取已发布文献下载链接
- **WHEN** 具有 `literature:read` 权限的 MCP 客户端请求已发布文献
- **THEN** 系统必须返回不含存储凭据的短期 PLAB 签名下载链接

#### Scenario: 签名链接访问未发布文献
- **WHEN** 签名链接指向的文献在访问时不是 `published`
- **THEN** 系统必须拒绝下载，即使链接签名本身有效

#### Scenario: 签名过期或被篡改
- **WHEN** 下载签名已过期或内容被篡改
- **THEN** 系统必须返回受控的不可用响应且不得访问远端对象存储

### Requirement: 文件上传和元数据处理解耦
系统 MUST 保持远端文件与上传记录成功后再处理元数据；元数据解析或提案失败不得回滚已成功的对象上传和上传记录。

#### Scenario: 元数据处理失败
- **WHEN** PDF 已写入选定后端且上传记录已保存，但后续元数据解析或提案失败
- **THEN** 系统必须保留远端对象和上传记录，并按现有流程记录或展示元数据失败

### Requirement: 既有记录只回填后端标识
数据库迁移 MUST 把既有 `UploadedDocument` 记录标记为 `nju_box`，不得复制、删除或探测其远端文件。

#### Scenario: 执行模型迁移
- **WHEN** 数据库应用新增 `storage_backend` 字段的迁移
- **THEN** 所有迁移前记录必须标记为 `nju_box`，且迁移过程不得访问 NAS 或 NJU Box
