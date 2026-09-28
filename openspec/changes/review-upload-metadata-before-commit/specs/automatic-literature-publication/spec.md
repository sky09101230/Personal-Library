## MODIFIED Requirements

### Requirement: Successful PDF uploads publish immediately
系统 SHALL 在 Browser 或 MCP 上传的正文 PDF 对象存储、上传者 metadata 确认和正式数据库登记均成功时，将对应文献标记为已发布，使其可被正式检索和下载。已有补充材料 SHALL 继续随所属正文的可见性展示，不独立创建或发布规范文献；本 Change 不重新启用补充材料自动识别。

#### Scenario: New PDF upload succeeds
- **WHEN** 用户上传一个新 PDF、确认其 metadata，且对象存储和正式数据库事务均成功
- **THEN** 系统保存正式上传记录并将对应文献标记为已发布

#### Scenario: Exact duplicate upload succeeds
- **WHEN** 用户确认的 PDF 与已有文献内容完全相同
- **THEN** 系统复用已有正式文献记录、关联当前上传者并保持其已发布状态

#### Scenario: Supplementary PDF upload succeeds
- **WHEN** 一份通过既有支持入口成功登记的补充材料已经关联正文文献
- **THEN** 系统不创建独立规范文献，该补充材料仅随所属正文的可见性展示
- **AND** Browser/MCP 的确认流程不因此启用补充材料自动识别

#### Scenario: File is staged but not confirmed
- **WHEN** PDF 已写入 NAS 暂存但上传者尚未确认 metadata
- **THEN** 系统不得将该项作为正式文献发布或暴露给正式检索

#### Scenario: MCP upload is confirmed in the browser
- **WHEN** MCP 上传者通过网页确认暂存批次且正式数据库事务成功
- **THEN** 系统发布正式文献并允许 MCP 正常检索该文献
