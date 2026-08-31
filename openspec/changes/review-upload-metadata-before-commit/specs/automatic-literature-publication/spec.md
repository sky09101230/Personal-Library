## MODIFIED Requirements

### Requirement: Successful PDF uploads publish immediately
系统 SHALL 在 Browser 或 MCP 上传的 PDF 对象存储、上传者 metadata 确认和正式数据库登记均成功时，将对应文献标记为已发布，使其可被正式检索和下载。

#### Scenario: New PDF upload and confirmation succeed
- **WHEN** 用户上传一个新 PDF、确认其 metadata，且对象存储和正式数据库事务均成功
- **THEN** 系统保存正式上传记录并将对应文献标记为已发布

#### Scenario: Exact duplicate confirmation succeeds
- **WHEN** 用户确认的 PDF 与已有文献内容完全相同
- **THEN** 系统复用已有正式文献记录、关联当前上传者并保持其已发布状态

#### Scenario: File is staged but not confirmed
- **WHEN** PDF 已写入 NAS 暂存但上传者尚未确认 metadata
- **THEN** 系统不得将该项作为正式文献发布或暴露给正式检索

#### Scenario: MCP upload is confirmed in the browser
- **WHEN** MCP 上传者通过网页确认暂存批次且正式数据库事务成功
- **THEN** 系统发布正式文献并允许 MCP 正常检索该文献
