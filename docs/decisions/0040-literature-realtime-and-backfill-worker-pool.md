# 0040 文献 realtime 与 backfill worker pool

## 决策

文献处理继续使用数据库队列，不在 Django Web 请求或上传 signal 中创建后台线程。新主 PDF 上传事务提交后，`transaction.on_commit()` 只创建 `mineru + realtime` job并立即返回；独立 `plab literature worker-pool` management command 常驻运行 5 个线程：1 个 realtime channel 使用专属 token，4 个 backfill channels 各使用一个独立 token。线程只存在于专用 worker 进程，不存在于 Web/ASGI 进程。

`DocumentProcessingJob` 增加 `queue_lane`、provider state、页/分段 progress、batch id、heartbeat 和 worker channel。PostgreSQL worker 使用 `SELECT ... FOR UPDATE SKIP LOCKED`，确保多个 channel 不领取同一 job；每个线程在处理前后关闭旧 Django connection，数据库连接保持 thread-local。SQLite 继续支持单 worker 开发与测试，但不运行 1+4 并发 pool。

realtime worker 只领取 realtime jobs，backfill workers 只领取 backfill jobs，因此历史积压不会阻塞新上传。job 只保存无 secret 的 channel label，不保存 token；token 通过 worker thread 的 context 注入 MinerU client。现有 `MINERU_API_TOKEN` 可作为 realtime token 的兼容 fallback，4 个 backfill token 必须单独配置且 5 个有效 token 必须互不相同。

MinerU client 在 allocation、upload、poll、download 和 normalization 阶段调用 progress callback。官方 `extract_progress.extracted_pages/total_pages` 按 segment page range 汇总到整个文档。详情页通过登录保护的 JSON endpoint 每 2 秒 polling，展示 queued、上传、页级解析、下载、normalizing、chunking、Overview、完成或失败；不引入 WebSocket、SSE、Celery、Redis 或消息中间件。

## Failure semantics

- 上传事务只负责原始 PDF 与轻量 enqueue；enqueue 失败会记录日志但不回滚 PDF。
- worker/token/API 不可用时 job 保持 queued 或进入 failed，Web 页面和上传后续操作不阻塞。
- progress 更新不包含 token、预签名 URL 或 provider error detail。
- worker 进程崩溃后的 running job recovery 仍沿用后续运维恢复范围，本变更不自动接管已提交的远端 MinerU batch。

## 非目标

不实现 Celery、Redis、Kafka、WebSocket、SSE、分布式 scheduler、全量自动 backfill、retrieval、embedding 或 RAG。5 个 token 是否共享 MinerU 账号总 quota 由官方账号策略决定，本地并发不承诺扩大额度。

