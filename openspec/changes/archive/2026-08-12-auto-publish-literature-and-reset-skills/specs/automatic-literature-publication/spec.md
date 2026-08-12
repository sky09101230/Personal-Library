## Purpose

确保用户成功上传的 PDF 无需管理员再次操作即可进入正式检索，同时保证存储或数据库失败的文件不会被误发布。

## ADDED Requirements

### Requirement: Successful PDF uploads publish immediately
系统 SHALL 在 PDF 对象存储和数据库登记均成功时，将对应文献标记为已发布，使其立即可被正式检索和下载。

#### Scenario: New PDF upload succeeds
- **WHEN** 用户上传一个新 PDF，且对象存储和数据库事务均成功
- **THEN** 系统保存上传记录并将对应文献标记为已发布

#### Scenario: Exact duplicate upload succeeds
- **WHEN** 用户上传的 PDF 与已有文献内容完全相同，且新附件登记成功
- **THEN** 系统将复用的文献记录保持或更新为已发布

### Requirement: Failed uploads are not published
系统 MUST NOT 因失败的上传创建已发布文献记录。

#### Scenario: Storage or database operation fails
- **WHEN** PDF 对象存储或数据库登记失败
- **THEN** 系统报告上传失败，且不存在由该失败操作产生的已发布文献
