## Purpose

让网页上传者在文件传输后、正式入库前检查并修正文献 metadata，防止错误或不完整记录直接进入共享文献库。

## ADDED Requirements

### Requirement: Uploaded files remain staged until uploader confirmation
系统 SHALL 将网页上传的 PDF 与解析结果归入当前用户的待确认批次，且在用户确认前不得创建正式文献或正式上传记录。

#### Scenario: A PDF finishes transfer and parsing
- **WHEN** 已登录用户上传有效 PDF，且 NAS 写入与 metadata 解析完成
- **THEN** 系统返回该文件的待确认解析结果
- **AND** 正式文献与正式上传记录均保持不变

#### Scenario: Another user addresses the batch
- **WHEN** 非批次上传者尝试查看、修改、确认或取消该批次
- **THEN** 系统拒绝该操作且不暴露批次内容

### Requirement: Browser upload uses four bounded channels
系统 SHALL 在批量上传时最多同时传输四个 PDF，并分别展示四个通道的当前文件和传输进度。

#### Scenario: More than four files are selected
- **WHEN** 用户选择超过四个 PDF 并开始上传
- **THEN** 浏览器同时上传不超过四个文件
- **AND** 每个文件完成后由空闲通道继续处理队列中的下一文件

### Requirement: Batch results expose metadata issues and corrections
系统 SHALL 在上传表单下方使用紧凑表格展示本批每个文件的解析结果，将缺少标题的项显示为错误状态，将缺少期刊的项显示为警告状态，并允许上传者编辑标题或提交 DOI 重新解析。

#### Scenario: All selected files finish parsing
- **WHEN** 本批所有上传 worker 均已完成
- **THEN** 浏览器将视口平滑滚动到本批 metadata 审核区
- **AND** 长文件名最多占用两行且可通过悬停查看全文

#### Scenario: Parsed title is missing
- **WHEN** 某个待确认项没有标题
- **THEN** 该项以红色错误状态显示
- **AND** 上传者可直接输入标题

#### Scenario: Parsed journal is missing
- **WHEN** 某个待确认项有标题但没有期刊名称
- **THEN** 该项以黄色警告状态显示

#### Scenario: Uploader reparses a DOI
- **WHEN** 上传者为待确认项提交格式有效的 DOI 并选择重新解析
- **THEN** 系统使用该 DOI 刷新可解析的 metadata 与证据
- **AND** 返回更新后的标题、期刊、作者和年份供上传者再次检查

#### Scenario: DOI reparse fails
- **WHEN** DOI 格式无效或外部 metadata 服务未返回可用结果
- **THEN** 系统保留原待确认项并显示受控错误
- **AND** 不创建正式文献记录

### Requirement: Confirmation gates formal database records
系统 MUST 仅在上传者确认批次后创建或关联正式文献记录；缺少标题的项 MUST 阻止整批确认，缺少期刊的项 MUST 保持黄色警告但可由上传者明确确认。

#### Scenario: Batch contains a missing title
- **WHEN** 上传者尝试确认仍有缺少标题的批次
- **THEN** 系统拒绝整批提交并保持所有项为待确认

#### Scenario: Batch has warnings but no missing title
- **WHEN** 上传者明确确认只有缺期刊警告、没有缺标题错误的批次
- **THEN** 系统在一个数据库事务中创建或关联正式文献和上传记录
- **AND** 将成功确认的新文献发布到正式文献库
- **AND** 浏览器在确认接口成功后进入 Library 页面

#### Scenario: Formal database transaction fails
- **WHEN** 确认期间任一正式数据库写入失败
- **THEN** 系统回滚本批全部正式数据库变更
- **AND** 保留待确认批次与 NAS 文件以允许重试

### Requirement: Uploader can cancel a pending batch
系统 SHALL 允许上传者取消未确认批次，并在远端删除成功后移除对应暂存记录。

#### Scenario: Pending batch cancellation succeeds
- **WHEN** 上传者取消待确认批次且所有 NAS 暂存文件均删除成功
- **THEN** 系统移除该批次的暂存记录且不创建正式文献记录

#### Scenario: Staged object deletion fails
- **WHEN** 取消批次时任一 NAS 暂存文件删除失败
- **THEN** 系统保留对应暂存记录并报告失败，避免丢失远端对象追踪信息
