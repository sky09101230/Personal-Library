## MODIFIED Requirements

### Requirement: 新文献使用配置的对象存储后端
系统 MUST 通过统一文献存储接口上传新文献，并将实际使用的后端标识与远端路径共同保存。缺少显式配置时，新文献后端必须为 `nas_webdav`；原始 PDF MUST 写入配置的 Literature root 下的 `originals/` namespace。

#### Scenario: 网页上传新文献到 NAS
- **WHEN** 已登录用户通过网页上传有效 PDF，且未显式选择其他文献后端
- **THEN** 系统必须将对象写入 NAS `Literature/originals/`，并将上传记录的后端保存为 `nas_webdav`

#### Scenario: MCP 上传新文献到 NAS
- **WHEN** 具有 `literature:write` 权限的 MCP 客户端上传有效 PDF
- **THEN** 系统必须使用与网页上传相同的 `originals/` namespace 和默认存储选择，并保存实际后端和远端路径

### Requirement: NAS WebDAV 适配器保护凭据和路径
NAS WebDAV 适配器 MUST 通过跳过服务器证书链和主机名验证的 HTTPS 与服务端 Basic Authorization 执行对象操作，必须拒绝不安全或越界的 root、namespace、source 和 destination 路径，且不得向网页或 MCP 响应暴露 NAS 凭据。该证书验证例外不得影响其他 HTTPS 客户端。

#### Scenario: NAS 使用不受信任且名称不匹配的证书
- **WHEN** NAS WebDAV 返回的证书链不受系统信任，或证书主机名与配置地址不匹配
- **THEN** NAS WebDAV 适配器必须继续建立加密连接并执行请求，且其他 HTTPS 客户端的证书验证行为保持不变

#### Scenario: 上传 namespaced 对象
- **WHEN** 适配器收到文件和合法 namespace
- **THEN** 适配器必须安全创建缺少的 namespace 目录，并以不会覆盖同名既有对象的随机路径执行 WebDAV PUT

#### Scenario: 上传对象
- **WHEN** 适配器收到有效 PDF 上传对象且未指定 namespace
- **THEN** 适配器必须以不会覆盖同名既有对象的随机路径在配置 root 下执行 WebDAV PUT，并返回持久化路径
- **AND** 文献应用层的新正文上传显式传入 originals namespace，不能因保留默认接口而退回旧布局

#### Scenario: 配置缺失
- **WHEN** NAS 地址、用户名、密码或文献 root 缺失或不合法
- **THEN** 系统必须在访问 NAS 前返回受控的文献存储配置错误

#### Scenario: 路径编码
- **WHEN** 远端路径包含空格、中文或其他需要 URL 编码的字符
- **THEN** WebDAV 请求必须对各路径段正确编码，且持久化路径保持可逆

#### Scenario: 同 root MOVE
- **WHEN** 适配器收到同一配置 root 内的合法 source 和 destination，且 destination 不存在
- **THEN** 适配器必须通过 WebDAV MOVE 移动对象并禁止覆盖 destination

#### Scenario: 越界或 traversal 路径
- **WHEN** namespace、source 或 destination 包含 traversal、反斜杠或落在配置 root 外
- **THEN** 适配器必须在发出远端请求前拒绝操作

## ADDED Requirements

### Requirement: Parser artifact 使用派生 namespace
系统 MUST 通过与原始 PDF 相同的 literature storage abstraction，把新 `DocumentParse` 完整 artifact 写入 `Literature/derived/parses/`，并将实际 backend 与远端路径保存到 parse 记录。

#### Scenario: 持久化新 parse artifact
- **WHEN** literature processing 成功序列化 PLAB 中立 parse artifact
- **THEN** artifact 必须写入 `derived/parses/` namespace
- **AND** 原始 PDF 仍保留在 `originals/` namespace

### Requirement: 既有 Literature 对象安全迁移到新布局
系统 MUST 通过显式运维命令迁移数据库引用的既有原始 PDF 和 parse artifact，不得通过 Django schema/data migration 访问远端 storage。迁移 MUST 支持 dry-run、重复执行和中断后继续，且不得覆盖或删除原始科研资料。

#### Scenario: Dry-run
- **WHEN** 操作者以 dry-run 执行布局迁移
- **THEN** 系统报告每条记录的确定性 source、destination 和计划动作
- **AND** 不执行 MOVE 或数据库更新

#### Scenario: 正常迁移一条对象
- **WHEN** source 存在且 destination 不存在
- **THEN** 系统以禁止覆盖的 MOVE 将对象移到保留原 basename 的目标 namespace
- **AND** 仅在 MOVE 成功后更新对应数据库 path

#### Scenario: 恢复 MOVE 后数据库未更新的记录
- **WHEN** source 不存在、destination 存在且数据库仍引用 source
- **THEN** 系统识别为中断后的迁移并只把数据库 path 修复为 destination

#### Scenario: 重复执行已完成迁移
- **WHEN** 数据库已引用目标 namespace 且目标对象存在
- **THEN** 系统将记录报告为已迁移并不执行远端写操作

#### Scenario: Source 与 destination 同时存在
- **WHEN** source 与 destination 都存在
- **THEN** 系统报告冲突并跳过该记录
- **AND** 不覆盖或删除任何一端

#### Scenario: Source 与 destination 都不存在
- **WHEN** source 与 destination 都不存在
- **THEN** 系统报告无法安全判断并跳过该记录
- **AND** 不修改数据库 path
