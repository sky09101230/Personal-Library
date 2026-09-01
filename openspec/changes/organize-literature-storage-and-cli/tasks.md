## 1. 规划与安全边界

- [x] 1.1 记录 storage namespace、MOVE 状态机、CLI adapter 和 non-goals ADR
- [x] 1.2 严格验证 OpenSpec proposal/spec/design/tasks 并独立提交规划

## 2. Storage Namespace 与新写入布局

- [x] 2.1 扩展现有 LiteratureStorage contract，支持安全 namespace、目录创建和确定性 object path
- [x] 2.2 实现 WebDAV exists 与禁止覆盖的同 root MOVE，并覆盖 traversal/编码/状态码测试
- [x] 2.3 将新原始 PDF 写入 originals，将新 parse artifact 写入 derived/parses
- [x] 2.4 运行 storage、upload、MCP 和 literature_processing 相关回归并独立提交

## 3. 可恢复的布局迁移

- [x] 3.1 实现 UploadedDocument 与 DocumentParse 的确定性 destination 规划和冲突检测
- [x] 3.2 实现 dry-run、MOVE 后更新数据库、断点恢复及条件更新语义
- [x] 3.3 覆盖正常 MOVE、重复执行、source missing/target present、双端存在和双端缺失测试
- [x] 3.4 提供稳定 storage migration service entrypoint 并独立提交

## 4. 统一 PLAB CLI

- [x] 4.1 提取旧/新命令共享的 worker loop service
- [x] 4.2 实现 plab literature backfill/enqueue/worker/status/process-existing
- [x] 4.3 实现 plab storage migrate-literature-layout 并保留旧命令兼容
- [x] 4.4 覆盖 CLI 参数、service delegation、输出和错误状态测试并独立提交

## 5. 当前 NAS 数据迁移

- [x] 5.1 在当前数据库/NAS 上运行 dry-run 并确认无不安全冲突
- [x] 5.2 执行实际布局迁移，记录 moved/recovered/already/conflict/error 汇总
- [x] 5.3 再次验证数据库全部目标 path 在 NAS 存在且 dry-run 无待 MOVE 项

## 6. 最终验证

- [x] 6.1 运行全量测试、Django check、migration drift 和严格 OpenSpec 校验
- [x] 6.2 审计未提交敏感数据、Phase 2 non-goals 和最终 Git 状态，并提交完成状态
