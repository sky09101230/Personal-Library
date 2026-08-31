## Why

Zotero 导入目前只创建 metadata 记录，用户仍需重复上传已经存放在 Zotero File Storage 中的 PDF。导入流程应在不扩大附件范围和不牺牲 metadata 成功率的前提下，将可用 PDF 一并写入现有文献存储。

## What Changes

- 对每个导入的 Zotero 顶层文献查询子附件。
- 仅下载 `linkMode=imported_file` 且 `contentType=application/pdf` 的 Zotero 托管文件。
- 跳过网页快照、URL 附件、非 PDF 和 `linked_file` 本地链接。
- 将成功下载的 PDF 写入现有 NAS 文献存储并创建关联同一规范文献的 `UploadedDocument`。
- 单个附件失败时保留 metadata、继续其他条目，并在实时进度和最终结果中报告失败数。
- 按规范文献和 SHA-256 复用已导入的相同 PDF，避免重复存储。

## Capabilities

### New Capabilities

- `zotero-pdf-attachments`: 定义 Zotero 托管 PDF 的筛选、下载、存储、去重和部分失败行为。

### Modified Capabilities

无。

## Impact

影响 Zotero Web API 读取、文献存储写入、`UploadedDocument` 创建、导入进度事件和结果统计。继续使用现有 Python 标准库、Django 文件对象和 NAS 存储接口，不增加运行依赖或数据库字段。
