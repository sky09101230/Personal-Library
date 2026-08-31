## ADDED Requirements

### Requirement: Uploaded PDFs retain their primary or supplementary role
系统 SHALL 为每条上传 PDF 记录正文或补充材料角色。正文 PDF SHALL 关联一个规范文献；补充材料 PDF SHALL 关联一个已有且带正文 PDF 的规范文献，且不得作为独立文献结果处理。

#### Scenario: Primary PDF is registered
- **WHEN** 一份正文 PDF 成功上传
- **THEN** 上传记录标记为正文并关联其规范文献

#### Scenario: Supplementary PDF is registered
- **WHEN** 一份补充材料成功上传并匹配到正文
- **THEN** 上传记录标记为补充材料并关联对应正文的规范文献

#### Scenario: Supplementary PDF is requested as a literature download
- **WHEN** 客户端请求一篇文献的默认 PDF 下载
- **THEN** 系统返回该文献的正文 PDF 而不是补充材料 PDF
