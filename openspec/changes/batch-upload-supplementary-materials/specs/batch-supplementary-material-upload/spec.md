## Purpose

让用户能够一次选择正文和补充材料 PDF；系统在写入正式存储前完成严格归属，并只保存可唯一附属到正文的补充材料，避免产生独立或待处理的补充材料记录。

## ADDED Requirements

### Requirement: Batch uploads resolve supplementary material against primary PDFs
系统 SHALL 在批量网页上传中，将已发布正文和同一批次中识别出的正文 PDF 一并作为补充材料的候选目标，并以 PDF 证据中规范化后的 DOI 进行唯一精确匹配。

#### Scenario: Supplementary material matches a primary PDF in the same batch
- **WHEN** 同一批次包含一份带有 DOI 的正文 PDF 和一份带有相同规范化 DOI 的补充材料 PDF
- **THEN** 系统先登记正文 PDF，再将补充材料登记为该正文所属文献的补充材料

#### Scenario: Supplementary material matches an existing primary PDF
- **WHEN** 补充材料 PDF 的规范化 DOI 唯一匹配到库中一篇已有正文 PDF 的文献
- **THEN** 系统将该补充材料登记为该文献的从属文件

#### Scenario: Candidate primary PDFs are not unique
- **WHEN** 补充材料的 DOI 在本批次和已存正文中不能确定唯一目标
- **THEN** 系统拒绝该补充材料且不创建对象存储文件或上传记录

### Requirement: Unmatched supplementary material is rejected before persistence
系统 MUST 在补充材料没有唯一且带正文 PDF 的目标文献时拒绝该文件，并且不得为该文件创建对象存储文件、上传记录或独立规范文献。

#### Scenario: No matching primary PDF exists
- **WHEN** 补充材料无法按 DOI 匹配到已存或同批次的正文 PDF
- **THEN** 系统报告“未找到对应正文，请先上传正文后再上传补充材料”
- **AND** 不保存该补充材料

#### Scenario: A primary PDF fails during batch persistence
- **WHEN** 某份同批次正文 PDF 未能成功存储或登记
- **THEN** 所有仅依赖该正文的补充材料均不保存

### Requirement: Batch results isolate per-file rejection
系统 SHALL 为批量上传中的每个文件报告成功或拒绝结果；未匹配补充材料的拒绝不得阻止同批次中已通过预检的正文或其他已匹配补充材料保存。

#### Scenario: One supplementary material is unmatched
- **WHEN** 同一批次中的一份补充材料未找到正文，而其他文件均已通过预检
- **THEN** 系统保存通过预检的文件
- **AND** 单独报告未匹配补充材料未上传
