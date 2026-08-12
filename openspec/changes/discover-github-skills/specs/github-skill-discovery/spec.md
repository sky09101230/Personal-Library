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
- **WHEN** 管理员在 3 分钟内重复提交相同关键词和页码
- **THEN** 系统复用缓存结果，不再次消耗 GitHub 搜索请求

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
