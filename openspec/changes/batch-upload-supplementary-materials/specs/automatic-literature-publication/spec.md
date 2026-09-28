## MODIFIED Requirements

### Requirement: Successful PDF uploads publish immediately
系统 SHALL 在正文 PDF 的对象存储和数据库登记均成功时，将对应文献标记为已发布，使其立即可被正式检索和下载。补充材料 PDF 成功登记时 SHALL NOT 独立创建或发布规范文献；它仅作为所属正文文献的从属文件可见。

#### Scenario: New PDF upload succeeds
- **WHEN** 用户上传一个新的正文 PDF，且对象存储和数据库事务均成功
- **THEN** 系统保存正文上传记录并将对应文献标记为已发布

#### Scenario: Exact duplicate upload succeeds
- **WHEN** 用户上传的正文 PDF 与已有文献内容完全相同，且新附件登记成功
- **THEN** 系统将复用的文献记录保持或更新为已发布

#### Scenario: Supplementary PDF upload succeeds
- **WHEN** 一份补充材料成功登记到已有正文文献
- **THEN** 系统不创建独立规范文献
- **AND** 该补充材料仅随所属正文的可见性展示
