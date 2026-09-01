## Context

参见 `proposal.md` 的动机。当前 `apps.box_upload` 已稳定拥有 `CanonicalDocument`、`UploadedDocument`、对象存储路由、PDF 上传事务和文献页面；仓库也已有 `select_for_update` claim 的数据库队列与 management command worker。新处理链必须复用这些边界，同时让上传模块不知道派生处理实现。

## Goals / Non-Goals

**Goals:**

- 形成从上传 PDF 到 page、chunk、overview、evidence 的可测试单向数据流。
- 允许 parser、chunker 和 prompt 独立升级，并保留每次成功或失败运行的历史。
- SQLite 本地开发和 PostgreSQL 部署使用同一组 Django 模型及迁移。
- 对详情 UI 采用项目组合层或新 App 自有视图，避免 `apps.box_upload` 的 Python 代码导入新 App。

**Non-Goals:**

- 不为 Phase 2 预建 embedding、索引、查询 API、RAG 或领域实体表。
- 不搬迁或重塑现有上传、metadata review、发布和 MCP 模型。
- 不保证扫描版 PDF 的 OCR；PyPDF 无文本页会被忠实保留为空页。
- 不实现 parser provider 的自动故障转移编排；Phase 1 只有明确的默认 PyPDF adapter。

## Decisions

### 1. 独立 App 与单向依赖

`apps.literature_processing` 可以导入 `apps.box_upload` 的模型和存储接口；`apps.box_upload` 不导入新 App。上传后自动 enqueue 由新 App 注册 `UploadedDocument.post_save` signal，并通过 `transaction.on_commit` 调用自身 enqueue 服务。UI 路由和视图由新 App 拥有，再复用现有文献页面结构与 PDF endpoint；必要的 URL 组合只发生在项目配置层。

备选方案是在 `save_pdf_upload()` 直接调用 enqueue，但这会造成明确的反向依赖并把 processing 可用性带入上传路径，因此拒绝。

### 2. 四类持久模型

- `DocumentProcessingJob` 外键指向 `UploadedDocument`，保存 queued/running/succeeded/failed 状态、当前 stage、pipeline/parser/chunker/prompt 版本、错误、时间戳和 attempt。数据库约束保证每个 upload 同时最多一个活动任务。
- `DocumentParse` 一对一指向 job，保存 parser 名称/版本、中立 schema 版本、页数，以及 artifact 的 backend/path/sha256/content type/size。每次重处理创建新 parse。
- `LiteratureChunk` 外键指向 parse，保存稳定 chunk key、全局顺序、页码、页内顺序、文本和内容哈希。Phase 1 块不跨页，从而让 evidence 页码无歧义。
- `DocumentAnalysis` 外键指向 parse 并可追溯 job，`analysis_type` Phase 1 仅允许 `overview`，保存通用 JSON payload、provider/model/prompt version/input fingerprint。模型验证 overview 结构与 chunk/page evidence 后才允许保存。

没有单独的 Evidence 表：Phase 1 的 evidence 是 overview key point 中的小型引用数组，引用同一 parse 的 chunk 主键和 page；增加第五个模型不会改善当前查询或完整性边界。

### 3. 中立 parser contract 与确定性 chunker

contract 使用不可变值对象表达 `ParsedPage(page_number, text)` 和 `ParsedDocument(schema_version, parser_name, parser_version, pages, metadata, warnings)`。PyPDF adapter 只在边界内接触 `pypdf.PdfReader`，清除 PostgreSQL 不接受的 NUL 字符，并为空页保留页号。未来 MinerU/Docling 只需新增 adapter，将其结果映射到相同 contract。

chunker 按规范化后的单页文本做确定性字符窗口切分，优先在段落/句末边界截断，使用固定 overlap；chunk key 由 page、页内序号和文本 SHA-256 组成。字符窗口不需要 tokenizer 依赖，且同版本输入可重复得到相同边界。

### 4. Artifact 存对象存储，查询单元存数据库

parser 中立结果序列化为 UTF-8 JSON，通过源上传记录所指 backend 的现有公开上传接口写入随机唯一对象路径；数据库同时保存 job UUID、artifact 索引和用于 UI/后续检索的 chunks。每次写入都创建新对象且不覆盖旧产物，不绕过 storage adapter 自行拼接远端路径。

备选方案把完整 JSON 放入 `JSONField`，会扩大 PostgreSQL 行、备份和常规查询负担；只存远端 artifact 又会迫使 UI 反复下载大文件。因此选择 artifact + chunks 双层保存。

### 5. 数据库队列、claim 与失败语义

enqueue 在事务中先复用同 upload 的活动任务；非 force 请求还会复用版本完全一致的最新成功任务。force 只在没有活动任务时追加新 job。worker 在短事务内 claim 最早 queued job，离开锁后执行 I/O；每个阶段以自己的原子数据库写入提交，异常统一写入 failed/stage/error_code/error_message。原始上传记录从不参加这些回滚事务。

SQLite 使用普通 `select_for_update` 语义，PostgreSQL 使用相同 ORM 路径；条件唯一约束负责并发下的最终幂等。backfill 只枚举 uploaded 状态的 primary PDF，并使用相同 enqueue 服务。

### 6. 非破坏性可见结果选择

旧 parse、chunks、analysis 不在重处理开始时删除。详情页只选择最新 succeeded job 的 parse 和 overview；新 job 运行或失败时，旧成功结果仍可展示，同时单独显示最新 job 状态。删除源 upload 时由现有保护关系决定是否允许，Phase 1 不自动删除远端派生 artifact。

### 7. AI Overview provider 边界

overview service 只接收带 chunk key、数据库 ID、page 和 text 的中立输入，provider adapter 返回 `summary_short`、`summary`、`topics`、`key_points`。保存前执行严格类型、长度和 evidence 所属关系校验；无效返回使 job 失败，不产生半合法 analysis。默认 provider 复用当前服务的 DeepSeek 配置约定，但 prompt 和 response parser 归新 App 所有，测试通过注入 generator 避免外网依赖。

AI Overview 永不写入 `CanonicalDocument.abstract` 或 metadata 字段。

## Risks / Trade-offs

- [PyPDF 对扫描件无文本] → 保留空页和明确 warning，不在 Phase 1 偷渡 OCR 基础设施。
- [signal enqueue 可能失败] → `on_commit` 回调使用安全包装并记录日志，上传事务已经成功且不会被回滚；backfill 可补偿遗漏。
- [JSON evidence 不能用数据库外键逐项约束] → `DocumentAnalysis.save/full_clean` 在唯一持久化边界检查 chunk 所属和页码，并以测试锁定；管理后台不开放任意新增/编辑。
- [远端 artifact 写入成功但数据库提交失败会留下孤儿] → 路径不可覆盖且派生数据可回收；Phase 1 记录明确前缀，为后续运维清理提供边界，但不做自动删除。
- [长文 overview 输入可能超过 provider 上限] → prompt builder 按页和 chunk 顺序使用固定上限，把截断标志纳入 provider packet 和输入指纹；Phase 1 UI 不单独展示该标志。
- [SQLite 并发锁语义弱于 PostgreSQL] → 单 worker 是默认运行方式，并用数据库唯一约束处理重复 enqueue；生产多 worker 行为由 PostgreSQL 测试/迁移约束保证。

## Migration Plan

1. 先部署新 App 和纯新增表迁移，不触碰原文献表中的数据。
2. 部署 parser/chunker、worker 和 backfill command；新上传在事务提交后开始排队。
3. 启动单个 processing worker，并用小批量 backfill 验证对象存储与错误率。
4. 部署 AI Overview 和详情 UI；未处理文献显示 pending/not queued，不影响 PDF 使用。
5. 回滚应用代码时保留全部新表和派生 artifact；它们不改变原始上传和 metadata，可在恢复新版本后继续处理。
