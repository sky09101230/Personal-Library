## Purpose

确保含 DOI 的新文献在任何文件写入 NAS 之前完成 BibTeX 请求预检，网络或服务失败时整批停止并向用户给出明确提示。

## ADDED Requirements

### Requirement: DOI BibTeX preflight precedes storage
系统 SHALL 在批次内任何文件写入对象存储之前，为每个需要新建规范记录且包含 DOI 的 PDF 获取并验证 BibTeX。

#### Scenario: All required BibTeX requests succeed
- **WHEN** 用户提交一个或多个 PDF，且所有需要执行的 DOI BibTeX 请求均成功返回有效 BibTeX
- **THEN** 系统继续上传整个批次

#### Scenario: A required BibTeX request fails
- **WHEN** 批次中任一需要执行的 DOI BibTeX 请求因网络、超时或无效响应而失败
- **THEN** 系统停止整个批次，且不写入任何 NAS 文件或上传数据库记录

#### Scenario: PDF has no DOI
- **WHEN** PDF 中未提取到 DOI
- **THEN** 系统不为该 PDF 执行 DOI BibTeX 预检，并允许其继续上传

### Requirement: Preflight failure is visible to the user
系统 MUST 在浏览器上传流程中以弹窗显示 DOI BibTeX 预检失败，并恢复上传按钮以允许重试。

#### Scenario: AJAX upload preflight fails
- **WHEN** 浏览器收到 DOI BibTeX 预检失败响应
- **THEN** 浏览器显示包含失败原因和停止上传结果的弹窗，不跳转页面，并恢复上传按钮以允许重试
