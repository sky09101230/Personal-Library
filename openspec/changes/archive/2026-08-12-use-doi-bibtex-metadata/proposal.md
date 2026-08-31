## Why

当前 PDF 上传只将文中提取到的 DOI 交给 Crossref JSON 接口，无法保留用户熟悉的 BibTeX 记录，也不能明确区分“BibTeX 原始字段”和“为补摘要而追加的字段”。需要把 DOI 解析后的 BibTeX 设为主要结构化来源，并在来源不完整或服务失败时保持可追溯、可复核的降级路径。

## What Changes

- 调整 PDF DOI 选择顺序：优先正文第一页、第二页，再使用其余已扫描页面与原始字节兜底，降低误选参考文献 DOI 的概率。
- 通过 DOI resolver 的内容协商请求 `application/x-bibtex`，解析并规范化标题、作者、期刊、年份、DOI、关键词和摘要。
- 当 BibTeX 缺少摘要或其他必要字段时，使用同 DOI 的 Crossref work 补齐；保留原始 BibTeX、补全来源和结构化证据。
- BibTeX 不可用时保留现有 Crossref 精确 DOI 回退；任一外部服务失败都不回滚已完成的 PDF 上传。
- 增加单元测试与真实 DOI 的只读联调，验证正常路径、摘要补全、冲突和回退行为。

## Capabilities

### New Capabilities

- `doi-bibtex-metadata`: 从 PDF 证据定位 DOI，通过 DOI 内容协商获得 BibTeX，并用同 DOI 的 Crossref 数据补齐缺失 metadata 的可追溯解析流程。

### Modified Capabilities


## Impact

- 代码：`apps/box_upload/metadata.py` 及其测试。
- 配置：新增 DOI resolver 基址；沿用 Crossref URL、mailto 与 HTTP timeout。
- 依赖：显式加入 `bibtexparser`，避免依赖其他包的传递安装。
- 外部系统：DOI resolver 与 Crossref REST API；不新增密钥或账号配置。
- 数据模型与迁移：无变更，证据继续写入现有 JSON 字段。
