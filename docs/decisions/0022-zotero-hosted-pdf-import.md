# 0022 Zotero 托管 PDF 导入

## 决策

Zotero metadata 落库后，逐篇读取子项，仅对 `itemType=attachment`、`linkMode=imported_file` 且 `contentType=application/pdf` 的附件调用 file endpoint。下载内容分块写入临时文件并同步计算 SHA-256，通过 PDF 签名检查后复用现有文献存储和 `UploadedDocument`。

## 失败与去重

单附件失败只记录进度和最终结果，不回滚已经导入的 metadata，也不阻断后续附件。相同 Canonical 下已有相同 SHA-256 时不重复写存储；远端写入成功但数据库记录创建失败时删除该远端对象。

## 边界

不下载网页快照、`imported_url`、`linked_url`、`linked_file` 或非 PDF；不增加后台任务、依赖、迁移或 Zotero 附件身份字段。
