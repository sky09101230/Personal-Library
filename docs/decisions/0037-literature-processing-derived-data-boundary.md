# 0037 文献处理派生数据边界

## 决策

新建 `apps.literature_processing`，只负责 `PDF -> parser -> parse -> chunks -> AI overview -> evidence`。`apps.box_upload` 继续独占原始 PDF、`CanonicalDocument`、`UploadedDocument`、书目 metadata、去重、审核和发布。依赖只能由 `literature_processing` 指向 `box_upload`；自动排队由新 App 的 signal 在上传事务提交后触发，UI 集成由新 App 和项目组合层提供，`box_upload` Python 代码不导入新 App。

数据库保存版本化的 `DocumentProcessingJob`、`DocumentParse`、`LiteratureChunk`、`DocumentAnalysis` 以及 parser artifact 的 backend/path/checksum 索引。完整 PLAB 中立 parse artifact 作为可重生成对象保存到源 PDF 对应的现有 NAS/object storage，不把 parser 专有大型响应塞入 PostgreSQL。chunks 保留 parse、页码、页内偏移和内容哈希；overview 与原文 abstract 分开保存，关键点必须引用同一 parse 的合法 chunk/page。

重处理采用追加新 job/parse/chunks/analysis 的方式，旧成功结果在新版本成功前继续可用，不先删除旧结果。派生记录随源 `UploadedDocument` 删除而级联删除，避免改变现有上传删除语义；Phase 1 不自动清理可能遗留的远端派生 artifact。

## 理由

原始科研资料是事实来源，parser 与 AI 输出会随实现和版本变化，二者必须具有不同的生命周期。独立 App 和 PLAB 中立 schema 可以让 PyPDF、未来 MinerU/Docling 与下游分块/分析解耦；数据库队列复用仓库已有运维方式，也能保证 processing 失败不回滚已成功上传的 PDF。

四个通用模型足以表达处理状态、一次解析、可追溯文本单元和领域无关分析。Phase 1 不增加 Evidence 表：overview payload 中的 chunk ID/page 引用由持久化边界严格校验即可，额外表不会提升当前行为完整性。

## Phase 1 非目标

本阶段不实现 embedding、pgvector 或独立向量库、语义/混合搜索、reranker、RAG、Knowledge Graph/GraphRAG、Skill runtime、Subagent/Multi-Agent、领域 ontology，也不加入 OCR 或 parser 自动故障转移。

## 已知限制

- PyPDF 不能为扫描版 PDF 执行 OCR，也不保留复杂版面结构；无文本页只保留页码和空文本。
- Overview 输入最多使用按顺序排列的 80,000 个 chunk 字符；截断标志进入 provider packet 和输入指纹，但 Phase 1 UI 不单独展示该标志。
- SQLite 以单 worker 运行为默认；Phase 1 没有自动恢复进程崩溃后遗留的 `running` job。
- 数据库提交失败时会尽力删除刚写入的派生 artifact，但远端删除再次失败可能留下孤儿对象；当前需按派生对象前缀人工清理。
- 只有 PyPDF adapter 已实现；MinerU/Docling 仅保留中立 contract 边界，没有运行时自动切换。

## Phase 2 边界

Phase 2 的检索输入只能来自已发布规范文献所关联的 `LiteratureChunk`，并保留 `chunk -> parse -> upload -> canonical document -> page` 追溯链。embedding、索引和检索结果必须是新的版本化派生数据，不得修改 chunk 文本、parser artifact、原始 PDF 或 bibliographic metadata；Phase 1 不预建这些表和服务。
