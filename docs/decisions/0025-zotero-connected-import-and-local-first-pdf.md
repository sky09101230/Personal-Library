# 0025 Zotero 连接式导入与本地 PDF 优先

## 决策

管理员先验证并保存 Zotero Web API 连接，再浏览 Collection（名称和 Key）、选择顶层条目并手动导入。API Key 使用由 Django `SECRET_KEY` 派生的 Fernet 密钥加密保存，每位管理员只保留一条连接，页面不回显明文。

## PDF 来源

对 Web metadata 中符合 `imported_file + application/pdf` 的附件，导入开始时先探测固定地址 `127.0.0.1:23119`。Zotero Desktop 可用时按同一附件 Item Key 读取其 `file://` 文件；任何本地读取或校验失败都回退现有 Web file endpoint，并继续复用同一套 PDF 签名、SHA-256、存储与失败隔离逻辑。

## 边界

不读取 linked file、网页快照、URL 附件或任意浏览器本地路径。Django 与 Zotero Desktop 不在同一主机时不支持自动读取用户电脑文件，只使用 Web 回退。
