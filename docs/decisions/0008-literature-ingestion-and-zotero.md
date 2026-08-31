# 0008 统一文献入口、证据化 metadata 与 Zotero 单向导入

## 决策

保留现有 `CanonicalDocument` 模型名，但将其语义明确为“规范文献实体”；`UploadedDocument` 仅表示 PDF 文件及一次上传记录。没有 PDF 的 Zotero 条目也可以成为规范文献，并通过 `ExternalReference` 保存 Zotero library、item key 与 version。

PDF metadata 采用保守解析：先保存原始文件和 SHA-256，再从 PDF 嵌入信息、前两页文本与原始字节中提取证据。只有提取到 DOI 且 Crossref 返回同一 DOI 时才可能标为 `verified`；无 DOI、查询失败或强冲突分别进入 `incomplete`、`needs_review` 或 `conflict`。外部服务失败不得回滚已经成功的 NJU Box 上传。

Zotero 首版采用 Web API v3 单向导入 metadata。API Key 只存在于当前 HTTP 请求，不写入数据库、日志或配置。导入记录默认 `needs_review`，不自动发布。双向同步、OAuth、附件下载与定时增量同步不属于本次变更。

文献发布状态与 metadata 状态分离。只有管理员明确设置 `index_status=published` 的规范文献才能通过 MCP 文献工具进入 Agent 上下文。

## 理由

文件不等于文献；同一文献可以有多个附件，也可以先有 Zotero metadata 后补 PDF。字段来源与复核状态必须可见，否则系统无法区分权威数据、PDF 线索和用户文献库中的脏数据。

第一版不引入 GROBID、DeepSeek 或任务队列，是为了先建立可验证的数据边界。现有 Django 请求内只做精确 DOI 的 Crossref 查询，无法确认时停止自动化而不是猜测。

## 约束

- 原始 PDF 仍只保存在 NJU Box，不写入仓库。
- `metadata_status=verified` 不等于 `index_status=published`。
- Zotero 导入不覆盖规范文献中已有的非空字段。
- Zotero API Key 不得持久化。
- MCP 列表、详情与下载都必须先过滤 `published`。
- 需要 OCR、标题候选检索或 LLM 重排时，应另建变更并用真实标注集校准阈值。
