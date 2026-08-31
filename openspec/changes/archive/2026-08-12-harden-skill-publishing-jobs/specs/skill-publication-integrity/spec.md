## Purpose

保证任何进入正式 Skill 列表和 Agent 上下文的内容都经过候选审核，并让后台扫描或补全任务在并发和异常退出后能够恢复。

## ADDED Requirements

### Requirement: 正式 Skill 只能由候选审核发布
系统 SHALL 只允许管理员审核通过候选快照后创建或更新正式 Skill 和 Release；不得提供从 GitHub 直接写入正式库的同步入口。

#### Scenario: 管理员扫描 GitHub 来源
- **WHEN** 管理员启动 GitHub 扫描
- **THEN** 系统只创建或刷新候选，不直接修改正式 Skill 或 Release

#### Scenario: 审核通过候选
- **WHEN** 管理员批准一个通过校验的候选
- **THEN** 系统从该候选快照创建正式 Release，随后正式 Skill 才可被检索

### Requirement: 元数据来自已发布版本
系统 SHALL 仅使用最新正式 Release 所记录 Git 提交中的 `SKILL.md` 生成正式 Skill 的摘要和分类，不得使用 GitHub 仓库中尚未审核的最新内容。

#### Scenario: 仓库领先于正式 Release
- **WHEN** GitHub 最新提交包含尚未批准的 Skill 修改且管理员启动元数据补全
- **THEN** 系统检出最新正式 Release 记录的提交生成元数据并记录该版本标识

### Requirement: 后台任务单例与过期恢复
系统 SHALL 通过数据库保证同一时刻最多存在一个排队或运行的 Skill 后台任务，并 SHALL 在新请求前将超过配置时限、未更新活动时间的任务标为失败。

#### Scenario: 两个并发启动请求
- **WHEN** 两个管理员请求同时启动后台任务
- **THEN** 数据库只允许一个新任务进入排队状态，另一个请求复用已存在任务

#### Scenario: 旧进程异常退出
- **WHEN** 排队或运行任务超过时限未更新活动时间，之后管理员再次启动任务
- **THEN** 系统先将旧任务标为失败并允许创建新任务

### Requirement: 后台任务活动时间可观察
系统 SHALL 在任务开始和每次进度更新时记录最近活动时间，并在任务失败时保留简短错误原因。

#### Scenario: 任务持续处理
- **WHEN** 后台任务完成一个可观察的进度步骤
- **THEN** 最近活动时间同步更新
