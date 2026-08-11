## Context

上传流程已经通过 `pypdf` 读取 PDF 嵌入信息与少量页面文本，并在找到 DOI 后直接请求 Crossref JSON。当前 DOI 搜索把原始 PDF 字节放在页面文本前，可能先命中参考文献；provider 证据只有 Crossref JSON，无法保留 DOI 对应的 BibTeX。系统已有 `metadata_evidence`、`metadata_candidates` 和 metadata 状态字段，因此无需迁移即可记录新证据。

## Goals / Non-Goals

**Goals:**

- 优先从 PDF 第 1 页、第 2 页定位 DOI，再有限兜底。
- 以 DOI resolver 返回的 BibTeX 作为主要结构化 metadata 来源。
- 用同 DOI 的 Crossref work 补齐 BibTeX 缺失摘要和必要字段，并显式记录字段来源。
- 在 resolver 或 Crossref 故障时保持上传成功，按证据强度进入已验证或待复核状态。
- 保留精确 DOI 校验、标题冲突检测和未发布隔离边界。

**Non-Goals:**

- 不引入 OCR、标题模糊检索、OpenAlex、Semantic Scholar 或出版商抓取。
- 不把 DeepSeek 生成的摘要冒充论文原始摘要。
- 不自动覆盖或批量重处理现有文献记录。
- 不改变发布、权限、MCP 检索或数据库模型。

## Decisions

1. **DOI 候选按证据位置排序。** 提取器记录每页 DOI 候选，选择顺序为第 1 页、第 2 页、其余已扫描页面、原始字节。相比只用正则首次命中，这能降低参考文献 DOI 抢占；相比扫描全文，仍保持请求内处理的成本边界。

2. **使用 DOI 内容协商获取 BibTeX。** 对规范化 DOI 请求 `${DOI_RESOLVER_URL}/{doi}`，发送 `Accept: application/x-bibtex`，限制 HTTPS、timeout 和最大响应体。相比按注册机构分别实现接口，resolver 保持单一入口。

3. **显式依赖 `bibtexparser==1.4.4`。** 解析 BibTeX 的转义、作者列表和常见字符串，而不是维护一次性正则解析器。解析结果先规范化，再映射到现有 canonical 字段。

4. **BibTeX 主来源，Crossref 精确补全。** BibTeX 字段优先；缺失 `abstract`、标题、作者、期刊或年份时才使用相同 DOI 的 Crossref 字段。Crossref 还用于 DOI 和标题交叉核验。若 BibTeX 不可用，沿用 Crossref-only 回退，保证旧能力不倒退。

5. **证据分层保存。** `metadata_evidence.bibtex` 保存有长度上限的原始/补全 BibTeX、解析字段和摘要来源；`metadata_evidence.crossref` 保留 provider 响应。DeepSeek 证据包只引用现有受控 provider 条目，不自动加入整段 BibTeX 原文。

6. **验证状态取决于可核验完整性。** DOI 必须一致；标题与 PDF 嵌入标题或 Crossref 标题严重不符时进入冲突。BibTeX 核心字段完整且 DOI 一致时可验证；缺字段、解析失败或仅有弱证据时进入待复核。外部服务错误不抛回上传事务。

## Risks / Trade-offs

- [PDF 正文没有 DOI 或为扫描件] → 保持 `incomplete`，不做模糊猜测；OCR 另建变更。
- [第 1 页包含多个 DOI] → 当前按页面内出现顺序选择并用 provider 标题核验；冲突时停止自动确认。
- [BibTeX 常缺摘要] → 仅用同 DOI 的 Crossref deposited abstract 补齐，并记录 `abstract_source`；仍缺失则留空。
- [resolver 返回非 BibTeX、超大或恶意内容] → 校验 HTTPS、响应大小、entry 结构和 DOI，不执行任何 BibTeX 内容。
- [新增网络请求增加上传耗时] → 沿用短 timeout；请求失败立即回退，不影响文件保存。

## Migration Plan

1. 增加显式 Python 依赖和环境变量示例，部署时安装 requirements。
2. 部署代码，无数据库迁移；新上传立即走新流程。
3. 用单元测试和一个公开 DOI 做只读联调。
4. 回滚时恢复旧 resolver 函数；现有 JSON 证据中的新增键不会影响旧代码。

## Open Questions

- 现有 22 篇文献是否批量重处理不属于本次自动部署；应在用户确认后单独执行并生成逐条结果。
