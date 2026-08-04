# GitHub 仓库准备清单

## 目标

建立一个可安全协作、不会存入科研数据或生产密钥的私有代码仓库。

## 已确认

- [x] 远程仓库已创建：`sky09101230/PLAB-Scientific-Agent`
- [x] 仓库可见性为 Private
- [x] 默认分支为 `main`
- [x] 采用单一 Monorepo
- [x] GitHub 不保存真实论文、实验数据、数据库和检索索引
- [x] 本地仓库已提供忽略规则、环境变量模板和贡献规范

## 待完成

- [ ] 将仓库转移到课题组 Organization
- [ ] Organization 至少配置两名长期 Owner
- [ ] 建立 `developers` Team 并按需授予 Write 权限
- [ ] 为 `main` 禁止 Force Push 和分支删除
- [ ] CI 建立后，将必要检查设为合并条件
- [ ] 有第二名开发者后，要求至少一人批准 Pull Request
- [ ] 配置备份或镜像策略

## 当前偏差

仓库目前属于个人账户 `sky09101230`，并非课题组 Organization。开发准备可以继续，但在邀请成员和正式部署前应完成仓库转移，避免项目长期绑定个人账号。

## Ready 标准

以下条件全部满足后，本项可标记为 Ready：

1. 本地能够认证、拉取和推送私有仓库。
2. `main` 的历史与远程一致，没有覆盖已有提交。
3. 至少一条 Pull Request 流程验证通过。
4. 密钥扫描确认仓库不包含真实凭据。
5. Organization 所有权和至少两名 Owner 已落实。
