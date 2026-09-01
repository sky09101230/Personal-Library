# 0038 Literature storage namespace 与统一 PLAB CLI

## 决策

继续以 `apps.box_upload.storage.LiteratureStorage` 作为唯一 literature 对象存储边界，在现有 NAS WebDAV adapter 内增加安全 namespace、目录存在性、对象存在性和同一 storage root 内 MOVE。新原始 PDF 使用 `originals` namespace，新 PLAB 中立 parse artifact 使用 `derived/parses` namespace；所有 namespace 都必须是相对 root、无空段、`.`、`..` 或反斜杠的路径。

既有对象通过独立运维 service 和 `python manage.py plab storage migrate-literature-layout` 迁移，不使用 Django schema/data migration。每条记录先检查 source/destination：只在 source 存在且 destination 不存在时 MOVE；只在 source 不存在且 destination 存在时把它识别为已 MOVE 未更新数据库的断点恢复；两端都存在或都不存在时报告冲突且不覆盖、不删除。数据库 path 只在远端 MOVE 成功或安全识别为已迁移后更新。

统一 CLI 只使用 Django `BaseCommand` 和子 parser 作为 adapter，调用 `backfill_processing()`、`enqueue_processing()`、`process_next_job()` 及 storage migration service，不引入 Click/Typer，也不复制 worker 或队列业务逻辑。旧命令保留兼容。

## 理由

原始科研资料和机器派生结果具有不同生命周期，远端目录应直接表达这一边界。把 namespace 与 MOVE 加入已有 adapter 可复用认证、路径校验和后端路由，避免第二套 WebDAV 客户端。外部对象状态不属于数据库 schema 演进，显式、可 dry-run 的运维命令比 migration 更安全，也能处理进程中断后的半完成状态。

## 非目标

本变更不设计 retrieval、embedding、vector database、semantic/hybrid search、reranker、RAG、Knowledge Graph/GraphRAG 或领域 ontology；不改变 parser、chunk、overview schema，也不引入新队列或 CLI framework。
