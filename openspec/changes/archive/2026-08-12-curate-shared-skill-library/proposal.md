## Why

当前 Skills 同步会把选定 GitHub 仓库中的全部 `SKILL.md` 直接发布，普通物理研究者又缺少无需 GitHub 的受控投稿入口；随着来源增多，正式库会迅速臃肿，而现有少量分类无法支持低成本筛选和维护。

## What Changes

- 新增统一的私有 Skill 候选池，GitHub 扫描和用户 ZIP 投稿都先进入候选池，未批准内容不进入正式检索、下载或 Agent 上下文。
- 普通登录用户可上传单 Skill ZIP，系统安全检查压缩包、定位唯一 `SKILL.md`、提取或补全展示元数据并提交审核。
- GitHub 来源改为先扫描候选清单，管理员按单个 Skill 选择发布，不再要求整仓导入。
- 复用现有 DeepSeek 摘要能力，为候选 Skill 建议科研任务分类；人工选择受保护，不被后续扫描覆盖。
- 扩充面向科研工作流的分类树，并将学科、工具等信息与主分类分离，避免把分类树无限细分。
- 管理员可筛选候选状态、批量批准低风险候选、拒绝或退回异常候选；批准时才复用现有 NAS Skill 发布链路。

## Capabilities

### New Capabilities

- `skill-library-curation`: 定义 ZIP 投稿、GitHub 候选扫描、安全校验、自动分类、人工审核和选择性发布行为。

### Modified Capabilities

无。

## Impact

- 影响 `apps/skills/` 的模型、服务、视图、表单、任务、管理命令和测试。
- 影响 Skills 页面、候选审核页和用户投稿页模板。
- 新增数据库迁移和一份技术决策记录；继续使用现有 Django、DeepSeek 调用、Git、ZIP 标准库和 NAS WebDAV 存储，不增加依赖。
- 现有已发布 `SharedSkill`、`SharedSkillRelease` 和下载接口保持兼容。
