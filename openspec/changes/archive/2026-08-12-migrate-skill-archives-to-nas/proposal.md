## Why

Skill 发布包仍存放在已弃用的 NJU Box，导致同步和下载继续依赖旧服务。将 ZIP 迁到现有 NAS，可让 Skill 与 Literature 使用同一受控存储基础设施，同时保留 SQLite 中的索引数据。

## What Changes

- 在 NAS 的 `/public/PLAB_KnowledgeBase/Skills` 创建与 `Literature` 同级的 Skill ZIP 目录。
- 新的 Skill 同步直接把 ZIP 写入 NAS，并在发布记录中标记实际存储后端。
- Web 页面和 MCP 下载根据发布记录从 NAS 或旧 NJU Box 读取，迁移期间不中断访问。
- 提供逐条迁移旧 ZIP 的命令；每个 ZIP 仅在 NAS 写入成功后更新数据库，失败时保留旧记录和旧文件。

## Capabilities

### New Capabilities

- `skill-archive-storage`: 定义 Skill ZIP 在 NAS 上的同步、下载、后端追踪和安全迁移行为。

### Modified Capabilities


## Impact

- 影响 `apps.skills` 的发布记录、同步服务、下载视图和管理命令。
- 影响 MCP 的 Skill 下载链接生成。
- 复用现有 NAS WebDAV 客户端和 SQLite 数据库；不新增依赖，不删除 NJU Box 原文件。
