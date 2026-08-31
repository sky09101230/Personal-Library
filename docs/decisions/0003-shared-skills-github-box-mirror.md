# 0003 Shared Skills GitHub-Box Mirror

## 决策

以 `sky09101230/PLAB-Shared-Skills` 作为组共享 Skill 的权威源。管理员手动同步指定 Git commit，将每个含 `SKILL.md` 的 Skill 打包为 ZIP 并写入独立的 NJU Box `PLAB Skills` 资料库根目录；Django 仅保存可检索元数据、commit 和 NJU Box 下载路径。

## 理由

GitHub 提供版本控制与评审，NJU Box 提供组内归档下载。单向同步避免 GitHub 与 Box 双向修改导致版本分叉。

## 约束

- 同步仅允许 Django staff 用户触发。
- 未同步版本不在 Skills 页面提供下载。
- Git commit、源路径和下载归档路径必须一并记录。
- `PLAB Skills` 使用独立的 repository ID；可配置独立加密密码，未设置时回退为文献库密码。
