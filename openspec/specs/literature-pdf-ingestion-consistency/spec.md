# literature-pdf-ingestion-consistency Specification

## Purpose
确保网页、MCP 和 Zotero 对同一份 PDF 给出一致、可解释的身份、发布、校验和权限结果，避免入口不同造成隐藏记录或越权操作。
## Requirements
### Requirement: 所有入口执行共同 PDF 边界
系统 SHALL 对网页、MCP 和 Zotero 提交的 PDF 执行同一文件大小上限和 PDF 内容签名检查；失败时不得留下对象存储文件或数据库上传记录。

#### Scenario: 伪装成 PDF 的文件
- **WHEN** 任一入口收到扩展名或声明为 PDF、但开头内容不含有效 PDF 签名的文件
- **THEN** 系统拒绝该文件且不创建上传记录

#### Scenario: 文件超过上限
- **WHEN** 任一入口收到超过配置上限的 PDF
- **THEN** 系统在写入正式存储前拒绝该文件

### Requirement: PDF 成功后立即发布
系统 SHALL 在 PDF 成功存储并建立上传记录后将对应文献设为已发布；只导入元数据而没有 PDF 的 Zotero 文献 SHALL 保持待审核。

#### Scenario: MCP 上传成功
- **WHEN** 有写入权限的 MCP 用户成功上传有效 PDF
- **THEN** 该文献可立即被正式文献检索读取

#### Scenario: Zotero 仅有元数据
- **WHEN** Zotero 条目导入成功但没有任何 PDF 成功入库
- **THEN** 新文献保持待审核且不进入 MCP 正式检索

### Requirement: 文献身份按可用证据合并
系统 SHALL 优先保留现有 Zotero 外部引用，随后按标准化 DOI 合并，缺少 DOI 时按 PDF SHA-256 合并；不得仅因文件名或标题相似而合并。

#### Scenario: MCP PDF 含已有 DOI
- **WHEN** MCP 上传的 PDF 解析出一个已有文献 DOI
- **THEN** 系统复用该文献而不创建第二个 CanonicalDocument

#### Scenario: PDF 没有 DOI
- **WHEN** PDF 没有可用 DOI 但 SHA-256 与已有文献一致
- **THEN** 系统复用已有文献

### Requirement: 关联者与实际上传者权限分离
系统 SHALL 将通过 DOI 等规则关联到用户的文献显示在“我的文献”，但 SHALL 仅允许实际创建过该文献 PDF 上传记录的用户或管理员审核元数据和删除相应附件。

#### Scenario: 仅关联用户查看文献
- **WHEN** 用户因重复 DOI 被关联到已有文献但没有创建 PDF 上传记录
- **THEN** 页面说明其为关联文献，且不显示该附件的审核或删除权限

#### Scenario: 实际上传者操作附件
- **WHEN** 用户拥有该文献的一条 PDF 上传记录
- **THEN** 用户可按现有安全删除规则删除自己的附件并参与元数据审核
