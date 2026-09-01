## Context

当前 NAS WebDAV adapter 把所有 literature 对象以随机 basename 直接写在配置 root，并只提供 PUT/GET/DELETE；`store_literature()` 和 parse artifact writer 共享该 root。现有 processing 已有版本感知 enqueue/backfill 与 database worker，但 management commands 分散。外部 NAS 状态不能由数据库 migration 原子管理。

## Goals / Non-Goals

**Goals:**

- 在唯一 storage adapter 内表达 originals 与 derived/parses namespace。
- 在不覆盖对象的前提下迁移既有 NAS 数据，并可从 MOVE/DB update 之间的中断恢复。
- 用一个 Django command 暴露常用 literature/storage 运维流程，同时复用 service。
- 实际迁移当前数据库引用，并留下可复核的 dry-run/执行摘要。

**Non-Goals:**

- 不改变 `UploadedDocument`、`DocumentParse` schema 或对象内容。
- 不复制对象、DELETE source 或提供跨 storage backend MOVE。
- 不设计 retrieval/vector/RAG 或新 worker infrastructure。
- 不引入 Click、Typer 或其他 CLI dependency。

## Decisions

### 1. Namespace 是现有 storage contract 的可选参数

`upload(file, namespace="")` 保留 root 上传兼容性，新增的 `store_literature()` 明确传 `originals`，parse artifact writer 明确传 `derived/parses`。adapter 校验 namespace 为安全相对路径，并逐级 PROPFIND/MKCOL 创建目录。这样上传、认证、随机命名、编码和错误语义仍只有一套。

备选方案是为 originals/derived 各建 storage class，但会复制 WebDAV 连接与安全逻辑，拒绝。

### 2. MOVE/exists 属于 storage primitive

adapter 增加 `exists(path)` 与 `move(source, destination)`。两条绝对路径都必须位于同一配置 root；MOVE 自动确保 destination parent namespace 存在，发送绝对 Destination URI 和 `Overwrite: F`。迁移 service 不直接构造 HTTP 请求。

### 3. 目标路径由 namespace 与现有 basename 决定

原始 PDF 目标为 `<root>/originals/<basename>`，parse artifact 目标为 `<root>/derived/parses/<basename>`。basename 为空、不安全或多条不同 source 映射到同一 destination 时作为冲突，不改远端或数据库。随机旧 basename 通常可直接保留，也让 dry-run 和重试得到相同结果。

### 4. 每条记录使用显式远端状态机

- 数据库已指向 destination：destination 存在则 already migrated；不存在则 conflict。
- source 存在、destination 不存在：dry-run 报 MOVE；实际执行 MOVE 成功后条件更新数据库旧 path。
- source 不存在、destination 存在：识别为 MOVE 已完成但数据库未更新，只条件更新数据库。
- 两端都存在或都不存在：conflict，绝不覆盖或删除。

数据库条件更新失败时重新读取记录；若已等于 destination 视为并发完成，否则报 error。若 MOVE 后数据库更新失败，下一次运行由第二种恢复分支修复。

### 5. 迁移是 application service，不是 migration

service 枚举 NAS backend 的 `UploadedDocument` 与 `DocumentParse`，返回逐条 action 和汇总；dry-run 也执行只读 exists 检查。Django migration 不访问网络。CLI 若存在 conflict/error，完成其余记录后返回非零状态并输出记录 ID/source/destination。

### 6. 统一 CLI 与 worker loop

`plab` command 使用 argparse subparsers。worker polling loop 提取成共享 service，旧 worker command 与新 CLI 都调用它；process-existing 组合 `backfill_processing()` 与同一 worker loop。status 统计逻辑放 processing service，CLI 不直接重写覆盖条件。

## Risks / Trade-offs

- [MOVE 成功后进程中断] → rerun 通过 source missing/destination present 修复数据库。
- [远端状态在 exists 后变化] → `Overwrite: F` 阻止覆盖；MOVE 非成功响应不更新数据库。
- [同 basename 冲突] → 报告并人工处理，不为追求自动化改名或覆盖科研资料。
- [大量对象产生多次 PROPFIND] → 迁移优先安全和可恢复；namespace 创建在实际执行时缓存，dry-run 不写远端。
- [process-existing 与已有队列交错] → 复用全局 FIFO worker，并在输出中分别报告 enqueue 与 processed；不建立第二套定向队列。

## Migration Plan

1. 部署 namespace-aware upload 和 parse artifact 写入，确保所有新对象直接进入新布局。
2. 运行单元/集成测试和 `plab storage migrate-literature-layout --dry-run`，冲突数必须为零后才执行。
3. 执行实际 migration；逐条 MOVE 成功后更新数据库。
4. 再运行 dry-run/verification，要求数据库引用的目标对象全部存在且无 legacy planned action。
5. 回滚应用代码不会移动对象；数据库 path 已指向真实位置，旧读取逻辑仍按记录 path 工作。不得反向 MOVE 或覆盖 originals。
