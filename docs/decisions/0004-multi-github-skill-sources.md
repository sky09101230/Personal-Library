# 0004 多 GitHub 来源的 Skills 广场

## 决策

将 GitHub 来源保存为 `GitHubSkillSource` 数据模型，由管理员在 Django Admin 中配置名称、仓库地址、分支和启用状态。`SharedSkill` 关联来源，Skills 广场按来源分区展示；同一来源内以 skill slug 唯一，不同来源允许存在同名 skill。

## 理由

单一环境变量无法表达多个仓库，也会在仓库出现同名 skill 时覆盖已有记录。来源进入数据库后，管理员可以独立启停和同步仓库，页面 URL 也能明确定位来源。

## 约束

- 同步只处理已启用的来源，并继续使用现有 NJU Box 镜像和下载链路。
- 新页面使用 `/skills/<source>/<skill>/`，保留无来源旧记录的兼容 URL。
- GitHub 仓库凭公开 HTTPS 地址读取；密钥和凭据不写入数据库或提交内容。
