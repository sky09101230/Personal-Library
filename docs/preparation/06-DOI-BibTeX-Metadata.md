# DOI → BibTeX metadata 准备

## 目标链路

新上传的 PDF 先由 `pypdf` 提取有限页面文本，从中选择 DOI；随后通过 DOI resolver 的内容协商取得 BibTeX。BibTeX 是标题、作者、期刊、年份、DOI、关键词和摘要的主要结构化来源。若其缺少摘要或必要字段，再请求同 DOI 的 Crossref work 补齐。

本次不引入 OCR、标题模糊检索、OpenAlex、Semantic Scholar 或出版商网页抓取。DeepSeek 生成内容也不得作为论文原始摘要写入 provider 证据。

## 依赖

- `pypdf==6.1.3`：读取 PDF 嵌入 metadata 和有限页面文本。
- `bibtexparser==1.4.4`：解析 BibTeX 转义、作者列表和常见字符串；作为直接依赖安装，不依赖其他包的传递安装。
- DOI resolver：HTTPS 内容协商，`Accept: application/x-bibtex`。
- Crossref REST API：按同一规范化 DOI 查询精确 work，仅补 BibTeX 缺失字段并做交叉核验。

安装：

```powershell
python -m pip install -r requirements.txt
```

无需新增数据库迁移。

## 配置

```dotenv
DOI_RESOLVER_URL=https://doi.org
CROSSREF_API_URL=https://api.crossref.org
CROSSREF_MAILTO=researcher@example.edu
METADATA_HTTP_TIMEOUT=5
```

`CROSSREF_MAILTO` 只用于形成可识别的 User-Agent；两项 metadata 服务均不需要 API Key。URL 必须为 HTTPS，响应体与保留的 BibTeX 证据都有大小上限。

## 失败与回退

- DOI resolver 失败、返回非 BibTeX 或解析失败：记录失败原因，并尝试现有 Crossref-only 精确 DOI 路径。
- Crossref 失败但 BibTeX 完整且 DOI 一致：保留 BibTeX 结果；能否自动验证取决于核心字段与 PDF 标题核验。
- 两者都失败：上传文件不回滚，metadata 保持待复核。
- PDF 无 DOI：保持不完整，不做标题猜测。

## 验收

- 单元测试证明第 1 页 DOI 优先于后页和原始字节。
- 单元测试证明 BibTeX 字段优先，Crossref 只补缺失摘要/字段。
- 单元测试证明 DOI 或标题冲突不会自动验证。
- 单元测试证明 resolver 失败时 Crossref-only 回退仍可用。
- 使用公开 DOI `10.1126/science.aat8084` 做只读联网联调，不写数据库。
