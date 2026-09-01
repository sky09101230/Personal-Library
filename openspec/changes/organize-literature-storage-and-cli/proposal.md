## Why

当前原始 PDF 与机器派生 parse JSON 混放在 Literature 根目录，生命周期和运维边界不清晰；同时文献处理命令分散，历史文献的常用处理需要记忆多个 management command。需要在不另建 storage 或队列系统的前提下整理远端布局，并提供一个薄的统一 CLI。

## What Changes

- 新上传的原始 PDF 写入 `Literature/originals/`，新 parser artifact 写入 `Literature/derived/parses/`。
- 扩展现有 WebDAV literature storage abstraction，增加安全 namespace、目录创建、对象存在性检查和同一 root 内的 `MOVE`。
- 增加可 dry-run、可重复、可断点续跑的外部 NAS 布局迁移 service，并在远端状态可安全判定后更新 `UploadedDocument.remote_path` 或 `DocumentParse.artifact_path`。
- 增加 `python manage.py plab ...` 统一入口，覆盖 literature backfill/enqueue/worker/status/process-existing 和 storage layout migration。
- 保留现有 `backfill_literature_processing`、`run_literature_processing_worker` 兼容入口；统一 CLI 只调用现有 service 层。
- 实际执行当前数据库所引用的 NAS 对象迁移并复核数据库与远端一致性。
- 不增加 retrieval、embedding、vector、RAG、GraphRAG 或新的 CLI framework。

## Capabilities

### New Capabilities

- `plab-management-cli`: 提供基于 Django management command 的统一 PLAB 运维入口，并复用现有 literature processing 与 storage service。

### Modified Capabilities

- `literature-object-storage`: 将新原始 PDF 和派生 parse artifact 写入分离 namespace，并支持安全、可恢复的 WebDAV MOVE 布局迁移。

## Impact

- 修改 `apps.box_upload.storage` 的现有 adapter contract、上传调用和 storage tests。
- 修改 `apps.literature_processing.artifacts` 的 artifact namespace，并新增外部布局迁移 service/tests。
- 新增 `plab` management command；旧 management commands 继续可用。
- 不创建 Django schema/data migration；现有数据库 path 仅在运维迁移命令确认远端状态后更新。
- 不增加第三方依赖。
