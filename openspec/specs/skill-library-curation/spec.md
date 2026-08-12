# skill-library-curation Specification

## Purpose
为科研用户和管理员提供统一、可审核的 Skill 候选流程，使本地 ZIP 与外部 GitHub 仓库中的 Skill 在进入正式库前完成安全校验、去重、摘要、分类和人工选择。
## Requirements
### Requirement: Unpublished candidates remain isolated
系统 MUST 将所有 ZIP 投稿和 GitHub 扫描结果保存为候选记录，并且候选在管理员批准前 MUST NOT 出现在正式 Skills 列表、下载接口或 Agent 检索上下文中。

#### Scenario: Pending candidate is not public
- **WHEN** 用户提交一个通过基础校验的 Skill ZIP
- **THEN** 系统创建仅投稿者和管理员可见的候选记录，且不创建正式 Skill 或正式发布包

### Requirement: Researchers can submit one Skill ZIP
系统 SHALL 允许登录用户上传一个只包含单个 Skill 的 ZIP，并自动定位唯一 `SKILL.md`、提取名称与描述、生成候选预览和投稿状态。

#### Scenario: Valid ZIP submission
- **WHEN** 登录用户上传包含唯一 `SKILL.md` 的有效 ZIP
- **THEN** 系统保存候选快照并在“我的投稿”中显示待审核状态、提取名称、摘要和建议分类

#### Scenario: Ambiguous ZIP submission
- **WHEN** ZIP 中没有 `SKILL.md` 或包含多个 `SKILL.md`
- **THEN** 系统拒绝投稿并以中文说明必须“一包一个 Skill”

### Requirement: ZIP validation protects the trust boundary
系统 MUST 在持久化或发布前限制 ZIP 大小、成员数和解压后体积，拒绝绝对路径、父目录跳转、符号链接、加密成员、敏感凭据文件以及项目禁止入库的论文、实验数据、数据库、向量索引和模型权重类型。

#### Scenario: Unsafe archive is rejected
- **WHEN** ZIP 包含路径穿越、符号链接、私钥、`.env`、PDF、实验数据、数据库或模型权重
- **THEN** 系统拒绝整个投稿，不写入候选存储，并返回不泄露文件内容的错误说明

#### Scenario: Oversized archive is rejected
- **WHEN** ZIP 超过配置的上传大小、成员数或总解压体积限制
- **THEN** 系统拒绝整个投稿且不尝试解压到文件系统

### Requirement: GitHub repositories are scanned before publication
系统 SHALL 允许管理员按来源扫描 GitHub 仓库，把每个发现的 `SKILL.md` 建为独立候选，而不是把整个仓库直接发布。

#### Scenario: Repository scan creates candidates
- **WHEN** 管理员扫描一个启用的 GitHub 来源
- **THEN** 系统刷新该来源的候选清单并记录仓库提交、Skill 路径和内容指纹，且不创建正式发布包

#### Scenario: Excluded candidate is not repeatedly reopened
- **WHEN** 已拒绝候选在后续扫描中的内容指纹未变化
- **THEN** 系统保留拒绝状态且不把它重新标记为待审核

#### Scenario: Upstream content changes
- **WHEN** 已拒绝或已发布候选的内容指纹发生变化
- **THEN** 系统将新快照标记为待审核，同时保留现有正式发布版本不变

### Requirement: Candidates receive normalized metadata and suggested classification
系统 SHALL 兼容缺失或常见变体 frontmatter 的 `SKILL.md`，使用目录名作为缺失名称的后备值，并复用现有 AI 流程生成两句中文摘要和一个现有叶子分类建议；AI 失败 MUST NOT 丢失候选。

#### Scenario: Metadata is incomplete
- **WHEN** `SKILL.md` 缺少名称、描述或标准单行 frontmatter
- **THEN** 系统用可恢复的本地规则生成名称，并在 AI 可用时补全摘要和分类

#### Scenario: AI enrichment is unavailable
- **WHEN** AI 配置缺失、超时或返回无效结果
- **THEN** 系统仍保留待审核候选、记录非敏感警告并允许管理员人工填写分类

### Requirement: Classification follows research tasks
系统 SHALL 提供以科研任务为主轴的分类树，至少覆盖文献与知识、数据分析与可视化、建模仿真与机器学习、实验仪器与硬件、科研写作与成果表达、科研工作流与工具集成，并保留现有文献检索和文献阅读分类。

#### Scenario: Existing literature categories are migrated
- **WHEN** 分类数据迁移执行
- **THEN** 现有 `literature-search` 和 `literature-read` 记录与其 Skill 关联保持不变，并成为“文献与知识”的子分类

### Requirement: Staff approve only selected candidates
系统 SHALL 允许管理员按状态和来源查看候选、调整叶子分类、批量批准可发布候选或拒绝候选；只有批准操作才能创建或更新正式 Skill 和 NAS 发布包。

#### Scenario: Candidate is approved
- **WHEN** 管理员批准一个校验通过且具有名称、摘要和分类的候选
- **THEN** 系统从该候选快照创建正式发布包和 Skill 元数据，记录发布关联，并把候选标记为已发布

#### Scenario: Candidate cannot be published
- **WHEN** 候选存在校验错误、缺少分类或与不兼容的正式 Skill 冲突
- **THEN** 系统拒绝批准且不产生部分数据库记录或孤立的正式存储对象

#### Scenario: Candidate is rejected
- **WHEN** 管理员填写原因并拒绝候选
- **THEN** 投稿者可看到拒绝状态和原因，候选不会进入正式库

### Requirement: Human decisions survive automation
系统 MUST 保留投稿者、GitHub 来源、提交版本、源路径、内容指纹、AI 生成信息和管理员最终决定；管理员手工选择的分类 MUST NOT 被后续扫描或 AI 补全覆盖。

#### Scenario: Manual category is preserved
- **WHEN** 管理员为候选选择分类后再次运行扫描或 AI 补全
- **THEN** 系统更新 AI 建议来源信息但继续使用管理员选择的分类

### Requirement: Candidate access is role scoped
登录用户 SHALL 只能查看自己的 ZIP 投稿，管理员 SHALL 能查看全部候选并执行扫描、分类、批准和拒绝操作。

#### Scenario: User opens another user's candidate
- **WHEN** 非管理员请求其他用户的 ZIP 候选详情
- **THEN** 系统返回不存在或无权访问，且不泄露候选元数据或存储路径
