## Purpose

为 PLAB 文献处理和对象存储运维提供一个可发现、可测试的统一 Django management command 入口，同时保持业务逻辑在既有 service 层中只有一份实现。

## ADDED Requirements

### Requirement: PLAB 提供统一 management command 入口
系统 SHALL 提供 `python manage.py plab` 命令，并使用分层子命令组织 literature 与 storage 运维操作。CLI MUST 只承担参数解析、service 调用和结果输出，不得复制业务逻辑或要求新的 CLI framework。

#### Scenario: 查看根命令帮助
- **WHEN** 操作者运行 `python manage.py plab --help`
- **THEN** 帮助列出 `literature` 和 `storage` 命令组及可用子命令

#### Scenario: 使用不支持的子命令
- **WHEN** 操作者传入未知命令组或子命令
- **THEN** Django management command 返回非零状态和可操作的 usage 信息

### Requirement: Literature CLI 复用当前 processing service
系统 SHALL 支持 `literature backfill`、`enqueue`、`worker`、`status` 和 `process-existing`，并 MUST 分别复用当前版本感知的 backfill、enqueue 和 database worker service。

#### Scenario: Backfill 历史 PDF
- **WHEN** 操作者运行 `plab literature backfill` 并给定 limit/force 参数
- **THEN** CLI 调用当前 backfill service 并报告 created/reused 数量

#### Scenario: Enqueue 指定 PDF
- **WHEN** 操作者运行 `plab literature enqueue --upload-id <id>`
- **THEN** CLI 调用当前 enqueue service 并报告 job、状态及是否新建

#### Scenario: Worker 处理队列
- **WHEN** 操作者运行 `plab literature worker`
- **THEN** CLI 通过当前 `process_next_job` pipeline 处理数据库队列，并支持 once、max-jobs 和 poll-interval 运行参数

#### Scenario: 查看处理状态
- **WHEN** 操作者运行 `plab literature status`
- **THEN** CLI 报告各 job 状态计数、可用主 PDF 总数和未被当前 pipeline 版本覆盖的数量

#### Scenario: 处理既有 PDF
- **WHEN** 操作者运行 `plab literature process-existing`
- **THEN** CLI 先通过当前 backfill service enqueue 未覆盖的历史 PDF，再通过当前 worker pipeline 处理队列
- **AND** 报告 enqueue 和 processing 结果

### Requirement: Storage CLI 暴露安全布局迁移
系统 SHALL 支持 `plab storage migrate-literature-layout` 并把 dry-run 参数和迁移结果传递给同一 storage migration service。

#### Scenario: CLI dry-run 布局迁移
- **WHEN** 操作者运行 `plab storage migrate-literature-layout --dry-run`
- **THEN** CLI 报告计划 MOVE、数据库恢复、已完成和冲突数量
- **AND** 不修改远端对象或数据库

### Requirement: 旧 processing commands 保持兼容
系统 SHALL 继续支持现有 `backfill_literature_processing` 和 `run_literature_processing_worker` 命令，并使其与统一 CLI 共享同一 service 实现。

#### Scenario: 运行旧 worker 命令
- **WHEN** 现有运维脚本调用旧 worker management command
- **THEN** 系统继续处理同一数据库队列且行为与统一 CLI worker 一致

