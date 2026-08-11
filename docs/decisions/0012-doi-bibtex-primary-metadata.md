# 0012 以 DOI BibTeX 为主要 PDF metadata 来源

## 决策

PDF metadata 解析在提取到 DOI 后，首先通过 DOI resolver 的 HTTPS 内容协商请求 `application/x-bibtex`，并将解析后的 BibTeX 作为主要结构化来源。BibTeX 缺少摘要、标题、作者、期刊或年份时，仅使用相同 DOI 的 Crossref work 填补空字段；不得用 Crossref 覆盖已有 BibTeX 字段，除非 DOI 或标题核验产生冲突并停止自动确认。

DOI 候选按 PDF 第 1 页、第 2 页、其余已扫描页面、原始字节的顺序选择。原始和补全后的 BibTeX、字段来源及 provider 错误保存在现有 `metadata_evidence` 中，并受长度限制。resolver 不可用时保留 Crossref-only 精确 DOI 回退。

## 理由

BibTeX 是科研工作流中可直接复用、可人工核对的交换格式。DOI resolver 内容协商为不同注册机构提供统一入口，而 Crossref deposited metadata 更适合补齐 BibTeX 经常缺失的摘要。两者分工并保留来源，比把多个 provider 字段无条件混合更可追溯。

页面优先的 DOI 选择能减少原始字节或参考文献 DOI 抢占首页论文 DOI 的风险，同时维持请求内有限解析，不扩大到全文 OCR。

## 约束

- 不自动批量重处理现有记录。
- 不把 AI 摘要标记为原始摘要。
- 外部 metadata 服务失败不得回滚 NJU Box 上传。
- metadata 验证状态不改变发布状态；只有明确 `published` 的文献进入 MCP Agent 上下文。
- 无 DOI 或证据冲突时停止自动化并交给上传者/管理员复核。
