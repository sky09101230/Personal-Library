## Purpose

确保 Skill 发布包能够安全存放在 NAS、通过 Web 页面和 MCP 下载，并在从旧 NJU Box 迁移时避免文件或索引丢失。

## ADDED Requirements

### Requirement: New Skill archives use NAS storage
系统 SHALL 将新生成的 Skill ZIP 写入与 Literature 同级的 NAS Skills 目录，并在发布记录中保存实际存储后端和远程路径。

#### Scenario: Synchronization creates a NAS release
- **WHEN** 已启用的 Skill 来源完成一次新提交同步
- **THEN** 系统将 ZIP 写入 NAS Skills 目录，并创建标记为 NAS 后端的发布记录

### Requirement: Skill downloads follow the recorded backend
系统 SHALL 根据每条发布记录的存储后端读取 ZIP，并 SHALL 同时支持 NAS 发布包和尚未迁移的 NJU Box 发布包。

#### Scenario: Web user downloads a NAS release
- **WHEN** 已登录用户下载标记为 NAS 后端的 Skill 发布包
- **THEN** 系统从 NAS 流式返回 ZIP，且下载文件名使用发布记录中的归档名称

#### Scenario: MCP client requests a Skill archive
- **WHEN** 有权限的 MCP 客户端请求 NAS Skill 发布包下载链接
- **THEN** 系统返回有时效限制的 PLAB 下载链接，而不暴露 NAS 凭据

#### Scenario: Legacy release remains readable
- **WHEN** 发布记录仍标记为 NJU Box 后端
- **THEN** 系统继续使用 NJU Box 下载流程读取该 ZIP

### Requirement: Legacy migration is loss-safe
系统 SHALL 逐条迁移旧 NJU Box ZIP，并且仅在对应 NAS 写入成功后更新该发布记录；迁移 SHALL 不删除或覆盖 NJU Box 原文件。

#### Scenario: One archive migrates successfully
- **WHEN** 系统成功从 NJU Box 读取一个 ZIP 并成功写入 NAS
- **THEN** 系统将该发布记录切换为 NAS 后端并保存新的远程路径

#### Scenario: One archive cannot be migrated
- **WHEN** NJU Box 读取或 NAS 写入失败
- **THEN** 系统保留该发布记录原有后端和路径，并报告失败
