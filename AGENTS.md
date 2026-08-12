# Repository Instructions

- 默认使用中文沟通和编写项目文档。
- 修改必须直接服务于当前任务，不顺手重构或扩展相邻内容。
- 每完成一个可独立提交且验证通过的修改，应立即创建 Git 提交，不积压多个改动。
- 原始科研资料不可覆盖；AI 生成内容必须与原始资料分开保存。
- 未发布内容不得进入正式检索或 Agent 上下文。
- 所有 Agent 结论必须能够追溯到文献、片段和页码。
- 不得提交真实密钥、账号密码、论文、实验数据、数据库备份、向量索引或模型权重。
- 新技术决策应记录到 `docs/decisions/`，编码前依赖应记录到 `docs/preparation/`。
- 如果仓库存在 `.codegraph/`，理解或定位代码时优先使用 CodeGraph。
- 实现功能前先定义可验证的验收条件；完成后报告已验证和未验证部分。

## OpenSpec CLI

- Codex 沙盒找不到 `openspec` 或拒绝执行 npm 全局 wrapper 时，不要因此重复初始化仓库。
- 请求非沙盒执行 `C:\Users\NewAdmin\AppData\Roaming\npm\openspec.cmd validate --all --strict --no-interactive`；PowerShell 拦截 `npm.ps1` 时改用 `npm.cmd`。
- 工具层缺失或过期时使用 `openspec update . --force`；仅首次初始化时使用 `openspec init . --tools codex`。
