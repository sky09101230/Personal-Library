## Purpose

让登录用户能够把正式 Skill 纳入自己的能力集合，并明确哪些 Skill 当前允许后续 Agent 流程使用，同时不越过现有候选审核和正式发布边界。

## ADDED Requirements

### Requirement: Users can add published Skills

系统 SHALL 允许登录用户从正式 Skills Discover 或详情页添加一个已发布的 Skill；同一用户对同一 Skill 的添加记录 MUST 唯一，重复添加 MUST 保持幂等。

#### Scenario: Install a formal Skill
- **WHEN** 登录用户提交某个正式 Skill 的添加操作
- **THEN** 系统创建该用户与 Skill 的唯一添加记录，并将其标记为启用

#### Scenario: Pending candidate cannot be installed
- **WHEN** 用户尝试通过添加接口提交不存在或未进入正式库的 Skill
- **THEN** 系统返回不存在，不创建任何添加记录

### Requirement: Users can manage their personal Skill library

系统 SHALL 提供登录用户专属的 My Skills 页面，展示其已添加的正式 Skill 及当前启用状态；用户 SHALL 能移除添加记录，并能独立启用或停用 Skill。

#### Scenario: View personal library
- **WHEN** 登录用户打开 My Skills
- **THEN** 页面只显示该用户自己的添加记录，并展示 Skill 来源、版本信息和启用状态

#### Scenario: Toggle enabled state
- **WHEN** 用户对已添加 Skill 提交启用或停用操作
- **THEN** 系统只更新该用户自己的添加记录，不影响其他用户或正式 Skill 元数据

#### Scenario: Remove installation
- **WHEN** 用户提交移除操作
- **THEN** 系统删除自己的添加记录，Skill 仍保留在正式 Discover 和其他用户的库中

### Requirement: Personal library actions preserve existing publication boundaries

系统 MUST 只允许登录用户管理正式 `SharedSkill`；候选记录、未审核内容、NAS 发布包和 MCP 可检索边界 MUST 不因添加、启用或移除操作而改变。

#### Scenario: Anonymous user is redirected
- **WHEN** 未登录用户访问 My Skills 或提交个人库操作
- **THEN** 系统要求登录，且不泄露个人添加数据
