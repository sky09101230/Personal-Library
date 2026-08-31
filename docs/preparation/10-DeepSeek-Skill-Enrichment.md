# DeepSeek Skill enrichment preparation

## Purpose

独立的摘要与分类任务克隆所选 GitHub 仓库并读取每个已导入 Skill 的 `SKILL.md`，由 DeepSeek 生成严格两句话的中文摘要，并从现有叶子用途分类中选择最匹配的一项。管理员只处理模型无法归类或需要纠正的例外。

## Required environment

复用现有 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 和 `DEEPSEEK_TIMEOUT`，不新增依赖或密钥。未配置 DeepSeek 时摘要与分类任务失败，不会把仓库原始 `description` 冒充为 AI 摘要，也不影响 GitHub 发布包同步。

## Data sent to DeepSeek

- Skill 名称；
- 当前已配置的叶子用途名称和 slug；
- `SKILL.md` 正文，最多 24000 个字符。

仓库文档按不可信数据处理；提示词要求忽略其中的指令，只做摘要和分类。API 密钥不进入提示词、数据库或日志。

## Verification boundary

自动测试注入模拟响应，不调用真实 API。真实摘要与分类任务会向 DeepSeek 发送上述有限内容，只更新 `SharedSkill` 与任务记录；流程不得调用 Skill archive storage。
