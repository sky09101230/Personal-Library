# Literature storage 布局迁移

## 目标布局

```text
Literature/
├── originals/
└── derived/
    └── parses/
```

新原始 PDF 由统一 literature storage adapter 写入 `originals/`；新 PLAB 中立 parse artifact 写入 `derived/parses/`。迁移不复制或 DELETE 对象，只在同一 WebDAV root 内使用 `MOVE`，并发送 `Overwrite: F`。

## 运维命令

```powershell
python manage.py plab storage migrate-literature-layout --dry-run
python manage.py plab storage migrate-literature-layout
```

只有 dry-run 不含 `conflict` 或 `error` 时才能执行实际迁移。实际命令可重复执行；若 MOVE 成功后进程在数据库更新前中断，下次运行会以 source missing / destination present 识别并修复数据库 path。

## 2026-09-01 执行记录

- 当前 PostgreSQL 尚未应用 `literature_processing.0001_initial`，先按 migration plan 应用了这一纯新增表 migration；该 Django migration 不访问 NAS。
- 首次 NAS dry-run：`would_move=634`，`conflict=0`，`error=0`。
- 实际执行：`moved=634`，`recovered=0`，`conflict=0`，`error=0`。
- 迁移后复核 dry-run：`already=634`，没有待 MOVE、冲突或错误。
- 634 条均为 `UploadedDocument` 原始 PDF；部署前没有 `DocumentParse` 数据，因此既有 parse artifact 迁移数为 0。

复核命令逐条检查数据库目标 path 在 NAS 存在。迁移没有覆盖、复制或删除任何原始科研资料。
