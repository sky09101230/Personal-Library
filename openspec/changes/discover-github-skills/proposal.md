## Why

当前管理员只能先手工配置 GitHub 仓库，再扫描整个仓库中的 Skills；面对分散在大量公开仓库中的 Skill，这一过程既慢又容易把无关内容塞进候选池。系统需要提供一个受控的 GitHub 发现入口，让管理员按关键词找到并只导入选中的 Skill。

## What Changes

- 在 Skills 区增加仅管理员可用的 GitHub Skill 搜索页面，固定搜索公开仓库中的 `SKILL.md`。
- 搜索必须提供 2 至 80 个字符的关键词，不提供空关键词全量搜索；每页 20 条，同一查询缓存 3 分钟。
- GitHub 搜索令牌只从服务器环境读取；限流或上游异常时显示可理解的错误，不连续重试。
- 管理员一次只能选择一个搜索结果导入；系统自动创建或复用来源记录，并只扫描该 Skill 目录。
- 导入前要求 GitHub 能识别明确许可证；无明确许可证时只保留 GitHub 查看链接。
- 搜索导入仍进入私有候选池，继续经过现有校验、摘要、分类和管理员发布流程。

## Capabilities

### New Capabilities

- `github-skill-discovery`: 管理员按关键词搜索公开 GitHub `SKILL.md`，检查许可证并将单个结果安全送入候选池。

### Modified Capabilities

无。

## Impact

- 影响 `apps.skills` 的页面、路由、GitHub 请求、后台扫描参数和测试。
- 增加 GitHub 服务端令牌环境变量说明，但不新增第三方依赖。
- 不新增搜索结果数据表，不改变正式 Skill 或 MCP 的发布可见性边界。
