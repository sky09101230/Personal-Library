## Why

当前文献模块负责原始 PDF、书目元数据与发布流程，但缺少与原始资料隔离、可重新生成且可追溯到页码的派生处理层。需要先建立稳定的 `PDF -> page -> chunk -> AI Overview -> evidence` 基础链路，后续检索能力才能在不污染原始科研资料的前提下复用统一文本单元。

## What Changes

- 新建单向依赖 `apps.box_upload` 的 `apps.literature_processing` Django App，明确原始资料与机器派生数据的边界。
- 增加版本化的处理任务、解析记录、可追溯文本块和通用 AI 分析模型。
- 定义 PLAB 中立 parser schema，并提供保留页码的 PyPDF fallback 与可替换 adapter 边界。
- 沿用数据库队列和 management command worker，支持上传后安全 enqueue、失败隔离、幂等重处理和历史 PDF backfill。
- 生成领域无关的 AI Overview，并在持久化前校验每个 key point 的 chunk/page evidence。
- 在现有文献详情页展示 processing 状态、AI Overview、Parsed Text 和证据页码。
- Phase 1 不增加 embedding、向量数据库、语义或混合搜索、reranker、RAG、知识图谱、Skill runtime、多 Agent 或领域 ontology。

## Capabilities

### New Capabilities

- `literature-processing`: 覆盖派生文献处理任务、版本化 PDF 解析与分块、AI Overview 证据校验、失败语义、backfill 及现有详情页展示。

### Modified Capabilities

无。

## Impact

- 新增 `apps/literature_processing`、数据库迁移、management commands、测试和详情页上下文/模板片段。
- 读取 `apps.box_upload.UploadedDocument` 及其现有对象存储接口，但不移动或修改 `CanonicalDocument`、`UploadedDocument` 的职责。
- 新增 PyPDF 解析依赖仅作为 adapter 实现；下游模型和服务只消费 PLAB 中立 schema。
- 完整 parser artifact 保存在现有对象存储，数据库保存 artifact 索引、页级/块级追溯信息和 AI 派生结果。
