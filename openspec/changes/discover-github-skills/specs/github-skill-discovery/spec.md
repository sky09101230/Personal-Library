## Purpose

让管理员在不预先配置大量仓库的情况下，按关键词发现公开 GitHub Skill，并把单个、许可证明确的结果安全送入现有私有候选审核流程。

## ADDED Requirements

### Requirement: 仅管理员可以发现 GitHub Skill
系统 SHALL 只向管理员开放 GitHub Skill 搜索和导入入口，普通用户不得使用对应页面或提交导入请求。

#### Scenario: 普通用户尝试访问
- **WHEN** 普通登录用户访问 GitHub Skill 搜索页或提交导入请求
- **THEN** 系统拒绝该请求，且不访问 GitHub、不创建来源或候选任务

### Requirement: 搜索范围受控
系统 SHALL 要求管理员输入 2 至 80 个字符的关键词，并固定搜索公开仓库中名为 `SKILL.md` 的文件；系统 MUST NOT 提供空关键词的全量搜索。

#### Scenario: 关键词为空或过短
- **WHEN** 管理员提交空关键词或少于 2 个字符的关键词
- **THEN** 页面显示校验提示，且不向 GitHub 发出请求

#### Scenario: 有效关键词搜索
- **WHEN** 管理员提交有效关键词
- **THEN** 系统每页最多显示 20 个匹配的 `SKILL.md`，并提示 GitHub 索引结果可能不完整

#### Scenario: 重复查询
- **WHEN** 管理员在 3 分钟内再次按搜索或翻页按钮提交相同关键词和页码
- **THEN** 系统复用缓存结果，不再次消耗 GitHub 搜索请求

#### Scenario: 刷新搜索结果页
- **WHEN** 管理员刷新、重新打开或复制当前搜索结果页的 GET 地址
- **THEN** 系统只显示当前会话中与关键词和页码一致的结果快照，不访问 GitHub 或 DeepSeek

#### Scenario: 只修改搜索地址
- **WHEN** 管理员手工修改 GET 地址中的关键词或页码但没有提交搜索或翻页按钮
- **THEN** 系统不访问 GitHub 或 DeepSeek，也不把不匹配的旧快照冒充为新结果

### Requirement: 搜索结果提供可解释的仓库热度与摘要
系统 SHALL 显示每个搜索结果所属仓库的 Star 数和最近代码更新时间，并在当前页内按 Star 从高到低排列；系统 SHALL 基于所列 `SKILL.md` 生成可追溯的两句中文 AI 摘要，但摘要失败不得阻断搜索和导入。

#### Scenario: 当前页结果排序
- **WHEN** GitHub 返回多个有效 `SKILL.md` 搜索结果
- **THEN** 系统显示其 Star 数和最近代码更新时间，并仅在当前页内按 Star、最近代码更新时间降序排列

#### Scenario: 相同文件再次出现
- **WHEN** 相同 blob SHA 的 `SKILL.md` 在摘要缓存有效期内再次出现在搜索结果中
- **THEN** 系统复用按文件版本保存的摘要，不再次读取文档或调用 DeepSeek

#### Scenario: AI 摘要不可用
- **WHEN** 单个文档无法读取，或 DeepSeek 未配置、限流、超时或返回无效内容
- **THEN** 页面仍显示 GitHub 结果、查看链接和候选导入操作，并明确标记摘要暂不可用

### Requirement: 管理员可以刷新学术 Skill 推荐
系统 SHALL 只允许管理员手动启动学术推荐刷新，从固定、非空且有限的学术关键词候选池中生成最多 10 条推荐；每条推荐 SHALL 显示推荐理由、Star 数、最近代码更新时间和 AI 评估时间。

#### Scenario: 管理员刷新推荐
- **WHEN** 管理员启动推荐刷新且 GitHub 与 DeepSeek 均成功完成
- **THEN** 系统原子替换推荐快照，并按 Star、最近代码更新时间降序展示适合学术研究的仓库

#### Scenario: 推荐刷新失败
- **WHEN** GitHub 或 DeepSeek 在生成完整推荐快照前失败
- **THEN** 系统将任务标记为失败并保留上一次成功推荐，不显示半成品或清空旧列表

#### Scenario: 普通用户访问推荐
- **WHEN** 普通用户访问推荐页或提交刷新请求
- **THEN** 系统拒绝请求，且不访问 GitHub 或 DeepSeek

#### Scenario: 推荐尚未导入
- **WHEN** 仓库只出现在学术推荐快照中
- **THEN** 系统不创建来源、候选、正式 Skill 或发布包，正式 Skills 检索与 MCP 均不可见该内容

### Requirement: GitHub 访问安全且可解释
系统 SHALL 只从服务器环境读取 GitHub 令牌，不得把令牌发送到浏览器；GitHub 限流、鉴权失败或服务异常时 SHALL 显示可理解的错误且不得自动连续重试。

#### Scenario: 令牌未配置
- **WHEN** 管理员发起搜索但服务器未配置 GitHub 令牌
- **THEN** 系统显示配置缺失提示，不泄露其他环境配置

#### Scenario: GitHub 限流
- **WHEN** GitHub 返回限流响应
- **THEN** 系统提示管理员稍后重试，并在可用时显示重置时间

### Requirement: 单项导入需要明确许可证
系统 SHALL 在导入时重新核对仓库、默认分支、目标 `SKILL.md` 和 GitHub 可识别的许可证；一次请求只能导入一个搜索结果。没有明确许可证的结果 SHALL 只能保留 GitHub 查看链接，不得进入候选池。

#### Scenario: 许可证无法识别
- **WHEN** 管理员选择的仓库没有 GitHub 可识别的许可证
- **THEN** 系统拒绝导入，且不创建来源、候选任务或正式 Skill

#### Scenario: 合法结果进入候选池
- **WHEN** 管理员选择公开仓库中存在的 `SKILL.md`，且仓库许可证可识别
- **THEN** 系统创建或复用来源记录，只扫描所选 Skill 目录，并把该结果送入现有私有候选流程

### Requirement: 发布边界保持不变
搜索导入产生的内容 SHALL 保持未发布状态，只有经过现有候选校验和管理员发布后才可进入正式 Skills 检索或 MCP。

#### Scenario: 导入任务完成但尚未审核
- **WHEN** 所选 GitHub Skill 已形成候选但管理员尚未发布
- **THEN** 正式 Skills 检索和 MCP 均不可见该内容
