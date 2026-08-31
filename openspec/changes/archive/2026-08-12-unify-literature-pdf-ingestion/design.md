## Context

网页上传已实现 DOI 预检、SHA 合并和自动发布；MCP 只按 SHA 合并且不发布；Zotero 有外部引用和 DOI 身份，但 PDF 保存逻辑独立且不发布。三个入口都直接写 `UploadedDocument`。

## Goals / Non-Goals

**Goals:**
- 复用一个最小 PDF 入库函数，统一校验、存储、事务和清理。
- 保留网页 DOI BibTeX 预检及 Zotero 外部引用逻辑。
- 让页面文字准确表达现有安全权限。

**Non-Goals:**
- 不改变注册、邀请码、密码或 TLS 配置。
- 不因重复 DOI 给关联者新增一条虚假的 PDF 上传记录。

## Decisions

### 共享函数接收已选定 canonical

身份信息来自不同入口：Zotero 已有外部引用，网页有 DOI 预检，MCP 需从 PDF 提取 DOI。各入口先选定 canonical，再把文件交给共享函数。这样保留已有证据链，不创建一套通用导入框架。

共享函数使用配置中的 MCP 上传上限作为全站 PDF 上限，流式计算 SHA-256、检查前 1024 字节内的 `%PDF-`、调用现有存储，再在事务中创建上传记录和发布 canonical。数据库写入失败时删除刚写入的对象。

### 关联不等于拥有附件

继续使用 `CanonicalDocument.uploaders` 表示文献关联，使用 `UploadedDocument.uploader` 表示实际提交者和操作权限。页面改名并展示关系，不改变安全规则。

## Risks / Trade-offs

- [旧测试用任意字节冒充 PDF] → 更新测试样本为最小 PDF 签名。
- [DOI 解析需要读取文件] → 复用现有可 seek 文件和元数据提取，不增加第二次网络存储。
- [同 DOI 并发提交] → 保留数据库唯一约束和事务后的对象清理。

## Migration Plan

无需数据库迁移；部署代码后新上传统一执行规则，已有记录不改写。
