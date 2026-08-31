# 0028 统一文献 PDF 入库与关联权限

## 决策

网页、MCP 和 Zotero 的 PDF 使用同一套大小上限、PDF 内容签名、SHA-256、对象存储、数据库事务和失败清理逻辑。身份优先使用入口已经确认的 Zotero 外部引用，其次使用标准化 DOI，缺少 DOI 时使用 SHA-256；不按标题或文件名猜测合并。

任何入口只要成功保存有效 PDF，就将对应文献设为 `published`。Zotero 只导入 metadata 而没有成功保存 PDF 时，文献继续保持 `pending`。

## 权限含义

`CanonicalDocument.uploaders` 表示与文献有关联的用户，`UploadedDocument.uploader` 表示实际提交某份 PDF 的用户。通过 DOI 等规则关联到已有文献的用户可以在“我的文献”中查看记录，但不会因此取得审核元数据或删除别人附件的权限。

## 边界

本次不修改注册、邀请码、密码策略或 NAS 证书验证，也不对既有文献做自动合并或回填。
