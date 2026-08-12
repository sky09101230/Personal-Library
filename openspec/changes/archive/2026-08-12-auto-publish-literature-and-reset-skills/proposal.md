## Why

新上传的 PDF 已经完成存储和数据库登记，却仍需管理员手动把文献标记为已发布，增加了无必要的操作。Skill 目录也需要一次受控清空和从既有 GitHub 来源重建，以移除当前全部发布包后获得干净状态。

## What Changes

- 新 PDF 上传事务成功时，立即将对应文献标记为已发布，使其可被 MCP 检索。
- 精简文献库中“等待管理员发布”的提示，但保留管理员在异常情况下调整发布状态的能力。
- 删除数据库引用的全部 NAS Skill ZIP；远程删除成功后才删除对应发布记录。
- 保留 GitHub 来源和同步配置，删除全部 Skill 后从现有 3 个来源重新同步。

## Capabilities

### New Capabilities

- `automatic-literature-publication`: 定义 PDF 上传成功即发布、失败不发布以及重复上传的行为。

### Modified Capabilities


## Impact

- 影响文献上传事务、文献库状态提示及上传测试。
- 对 Skills 执行一次破坏性数据清理和重新同步；不删除 GitHub 来源配置。
- 复用现有 NAS WebDAV 删除、Skill 同步和下载实现，不新增依赖。
