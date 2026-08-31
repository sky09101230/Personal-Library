## Why

网页、MCP 和 Zotero 三个入口现在对同一份 PDF 使用不同的去重和发布规则，导致“上传成功但 MCP 看不到”以及“显示为我的上传却不能审核”的混乱。

## What Changes

- 三个入口统一按外部引用、DOI、SHA-256 的可用程度识别同一篇文献。
- 所有通过 PDF 内容校验并成功落盘的文献都立即发布；只有元数据、没有 PDF 的 Zotero 文献继续待审核。
- 复用一套 PDF 大小、签名、存储、数据库写入和失败清理逻辑。
- 页面区分“我实际上传的 PDF”和“因 DOI 等规则关联到我的文献”；仅实际上传者或管理员可审核、删除附件。
- 不改注册、邀请码、密码策略或 NAS 证书连接。

## Capabilities

### New Capabilities

- `literature-pdf-ingestion-consistency`: 定义所有入口共同的 PDF 校验、身份识别、发布和上传者权限行为。

### Modified Capabilities

无。

## Impact

- 影响 `apps/box_upload/`、`apps/mcp_gateway/` 及文献列表模板和测试。
- 不增加依赖；不修改现有数据库结构。
