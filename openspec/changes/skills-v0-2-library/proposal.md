## Why

当前 Skills 页面能发现和查看正式 Skill，但用户没有自己的 Skill 库，无法表达“已添加”和“允许 Agent 使用”的状态。V0.2 先补齐这条最小用户闭环，让发现结果可以被安全地加入个人能力集合，同时保持候选审核和正式发布边界不变。

## What Changes

- 为登录用户增加个人 Skill 添加记录，并区分已添加与启用状态。
- 在 Discover 和 Skill Detail 提供添加/移除入口；添加只针对已发布的正式 Skill。
- 增加 My Skills 页面，展示用户已添加 Skill，并支持启用/停用。
- 在现有 Skills 导航中加入 Discover、My Skills 入口；保留管理员精选、投稿和候选审核入口。
- 为上述行为增加最小模型、视图、路由、模板和回归测试。
- 不引入推荐算法、评分、运行编排、复杂版本选择或改变候选发布规则。

## Capabilities

### New Capabilities

- `skill-personal-library`: 用户添加、启用、停用和移除正式 Skill，并查看个人 Skill 库。

### Modified Capabilities

无。现有 `skill-library-curation` 的候选隔离、管理员审核和正式发布规则保持不变。

## Impact

- `apps/skills`：新增用户添加模型、个人库与状态变更视图、路由及测试。
- `templates/skills`、`templates/base.html`：增加页面导航、卡片动作和个人库页面。
- 数据库：新增一次 Skills 迁移；不修改现有候选或正式 Skill 数据。
- 不新增第三方依赖，不改变 MCP 的已发布内容边界。
