## Context

上传流程在对象存储成功后，于数据库事务中创建或复用 `CanonicalDocument` 并创建 `UploadedDocument`。正式 MCP 检索以 `index_status=published` 为边界；当前默认值为 pending，因此需要管理员再次修改。Skills 当前有 366 条发布记录，指向 NAS Skills 根目录下 360 个唯一 ZIP。

## Goals / Non-Goals

**Goals:**

- 让上传事务成功成为自动发布的唯一触发点。
- 清理 Skill 时先删除 NAS 对象，再删除数据库行，随后从现有来源重建。

**Non-Goals:**

- 不自动发布仅由 Zotero 导入、没有 PDF 上传的记录。
- 不删除 GitHub 来源、访问配置或用户账户。
- 不新增永久性的“重置 Skills”框架。

## Decisions

1. 在现有上传数据库事务内把 canonical 的 `index_status` 设置为 `published`。这同时覆盖新文献和精确重复上传，并利用现有事务保证数据库失败时回滚。
2. 保留管理员修改发布状态的能力，用于异常下架；只移除“每次上传都需管理员发布”的流程和提示。
3. Skill 清理是一次运维动作：按唯一 NAS 路径删除，远程删除成功后再删除引用该路径的发布记录。全部发布记录清理成功后，通过级联删除 Skill，并保留 GitHub 来源。

## Risks / Trade-offs

- [NAS 删除部分失败] → 保留失败路径对应的数据库记录和 Skill，不声称清理完成。
- [多条发布记录共享一个 ZIP] → 按唯一路径只删除一次，再删除该路径的所有引用。
- [重新同步部分来源失败] → 保留已成功的新数据并报告失败来源，不掩盖覆盖率缺口。

## Migration Plan

1. 部署上传即发布代码和测试，并将现有带已上传 PDF 的 pending 文献一次性设为 published。
2. 校验所有待删 ZIP 均位于配置的 Skills 根目录。
3. 删除 360 个唯一 NAS ZIP；成功后删除 366 条发布记录及 183 个 Skill。
4. 从保留的 3 个 GitHub 来源重新同步，并验证每个 Skill 都有 NAS ZIP。
