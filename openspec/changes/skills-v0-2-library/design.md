## Context

现有 `apps.skills` 已将候选记录与正式 `SharedSkill` 分开，并要求登录后访问 Skills 页面；正式 Skill 通过 `SharedSkillRelease` 关联发布包。当前没有用户级添加状态，因此 Discover 只能表达公共目录，无法形成个人能力集合。

## Goals / Non-Goals

**Goals:**

- 用一张最小的用户—正式 Skill 关系表表达添加和启用状态。
- 复用现有详情页、卡片、登录和 CSRF 约束，提供 Discover、Detail、My Skills 三个入口。
- 保持添加操作只引用正式 `SharedSkill`，不触碰候选发布流程或 MCP 查询边界。

**Non-Goals:**

- 不实现推荐、评分、评论、运行编排、权限分级或复杂版本选择。
- 不把 Skill ZIP 内容复制到用户空间；添加只记录数据库关系。

## Decisions

- 新增 `SkillInstall`，字段为用户、正式 Skill、`enabled`、创建和更新时间，并对 `(user, skill)` 建唯一约束。这样添加状态与公共 Skill 元数据解耦，移除不会删除共享资产。
- 添加默认启用；停用只改变该用户的布尔状态。相比拆成多张状态表，单表直接对应 V0.2 的可观察行为。
- 添加、移除、启停均使用登录保护的 POST 接口并带 CSRF；对象查询限定当前用户，避免越权修改其他用户的记录。
- Discover 卡片显示已添加状态和添加/移除动作，Detail 提供同样的状态操作，My Skills 复用现有卡片样式展示管理动作。
- 不增加新的依赖或 API 层；使用 Django ORM、模板和现有消息提示。

## Risks / Trade-offs

- [Risk] 删除添加记录后无法保留用户历史 → V0.2 明确只需要当前能力集合；若未来需要审计，再增加独立事件记录，不污染当前关系表。
- [Risk] Skill 被管理员删除会级联删除添加记录 → 正式 Skill 当前没有软删除语义；页面只展示仍存在的正式 Skill，后续若引入下架需求再定义迁移。

## Migration Plan

新增一次 Skills 数据库迁移，默认不生成任何添加记录，因此不会改变现有用户或正式 Skill。回滚时删除迁移和对应代码即可，不触碰候选或发布包数据。
