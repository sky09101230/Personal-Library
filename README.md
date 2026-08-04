# PLAB Scientific Agent

PLAB Scientific Agent 是面向课题组内部的科研知识沉淀、检索与智能问答平台。

项目目前处于**编码前准备阶段**，尚无可运行的业务代码。当前工作重点是确认 GitHub、数据库、AI 检索、Web 部署和测试样本的前置条件。

## 第一阶段目标

打通一条可验收的文献闭环：

```text
上传 PDF → 后台解析与 AI 摘要 → 上传者审核 → 发布 → 检索 → 带页码引用的 Agent 回答
```

## 文档入口

- [系统宏观架构](docs/architecture/00-Architecture.md)
- [技术决策记录](docs/decisions/0001-monorepo.md)
- [GitHub 准备清单](docs/preparation/01-GitHub-Readiness.md)
- [贡献指南](CONTRIBUTING.md)
- [安全说明](SECURITY.md)

## 数据边界

GitHub 只保存平台源代码、文档、测试和部署配置。以下内容不得提交：

- 真实论文、实验数据和用户上传文件
- 数据库备份、检索索引和模型文件
- API Key、密码、令牌和生产环境配置

科研原始文件存放于 NJU Box，业务状态存放于 PostgreSQL，检索索引必须能够重建。

## 仓库状态

- 默认分支：`main`
- 仓库形态：私有 Monorepo
- 业务代码：尚未开始
- 下一阶段：完成编码前准备清单
