## Context

Skill 元数据和索引位于本地 SQLite；183 条发布记录的 ZIP 位于 NJU Box。现有 NAS WebDAV 客户端已经负责 Literature 的 PUT、GET 和 DELETE，但默认根目录固定为 Literature。Skill 下载有登录页面和 MCP 临时链接两条入口。

## Goals / Non-Goals

**Goals:**

- 复用现有 WebDAV 客户端，在 `/public/PLAB_KnowledgeBase/Skills` 存放 ZIP。
- 新同步不再依赖 NJU Box。
- 迁移逐条提交，任一失败不损坏原记录。

**Non-Goals:**

- 不迁移 SQLite 数据库文件。
- 不删除 NJU Box 原 ZIP。
- 不引入通用对象存储框架或新依赖。

## Decisions

1. `SharedSkillRelease` 新增 `storage_backend`，现有记录数据迁移为 `nju_box`，新记录写 `nas_webdav`。保留现有 `repository_id` 字段以兼容旧发布包；无需重做唯一约束。
2. 直接以不同 `root` 实例化现有 NAS WebDAV 客户端，并增加幂等根目录创建。相比复制一套 Skill 存储类，这保持验证、认证和路径约束只有一份。
3. 页面下载对 NAS 使用 Django 流式响应；MCP 使用带时效签名的 PLAB URL。旧 NJU Box 发布包继续走现有临时链接流程。
4. 迁移命令优先把单个 NJU Box 流写入临时文件；当旧服务不可连接时，可按发布记录的 Git 提交和 Skill 路径重建 ZIP。两种方式都在 NAS 上传成功后才更新该行，且复用已存在的同提交 NAS 包。

## Risks / Trade-offs

- [NJU Box 当前不可连接] → 命令保留未迁移记录并输出成功/失败计数，可在服务恢复后重跑。
- [迁移期间同一提交同时存在新 NAS 发布记录] → 命令跳过冲突记录并报告，不删除任何行。
- [NAS 根目录不存在] → 同步和迁移前执行幂等目录创建。

## Migration Plan

1. 应用数据库迁移，将已有发布记录标记为 `nju_box`。
2. 配置 `NAS_WEBDAV_SKILLS_ROOT=/public/PLAB_KnowledgeBase/Skills` 并创建目录。
3. 部署双后端下载和 NAS 新同步。
4. 运行旧 ZIP 迁移命令；若 NJU Box 不可连接，使用 `--rebuild-from-git` 按原提交重建；核对成功、失败和剩余 NJU Box 记录数。
5. 回滚时停止迁移并恢复新同步配置；尚未迁移的记录始终可按旧后端读取，已迁移记录可继续从 NAS 读取。
