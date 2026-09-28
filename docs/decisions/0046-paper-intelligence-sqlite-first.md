# 0046 Paper Intelligence V1 先用 SQLite

日期：2026-09-28。状态：已决定，按用户要求调整实施计划。

## 决策

Personal-Library 与 Paper Intelligence V1 先在现有 SQLite 环境开发、测试和运行。延续 [0042 本地存储决策](0042-local-filesystem-storage.md)，不要求先部署 PostgreSQL；PostgreSQL 不作为六个 V1 Changes 启动或完成的前置条件。

V1 必须在 SQLite 上通过真实迁移、唯一/条件约束、幂等与并发状态更新测试。使用 Django ORM 和可移植字段/约束，不引入 PostgreSQL 专属 SQL、pgvector 或全文检索依赖。网络与模型调用位于写事务外，事务保持短小；不能依赖 SQLite 不具备的行级 select_for_update 锁。

PostgreSQL 兼容是后续切换目标，不在未实测时声称已经通过。当前单机使用 SQLite；将来需要更多并发写入或部署到多实例时，再安排独立迁移任务。

## 后续迁移边界

切换数据库不仅是修改连接配置，必须完成一次可回退的数据搬迁：

1. 在可丢弃的 PostgreSQL 测试实例应用 Django migrations，导入一致性备份并测试；不直接对正式数据试迁。
2. 正式切换时停止网页写入和所有 worker，保存 SQLite、配置与文件存储的一致性备份。迁移窗口内禁止双写。
3. 转移业务数据并保留主键、外键和 UUID，特别是 DocumentParse、LiteratureChunk、DocumentAnalysis、conversation/message/run 的身份。处理 Django content types/permissions 的目标库映射，并重置自增序列，防止导入后新记录碰撞。
4. 对比行数、关系、JSON payload、source hash、parse/Evidence ID 和资产路径；原 PDF 与派生文件留在原存储，迁移不要求重新解析或改写 Evidence。
5. 验证登录权限、旧新 Overview、对话、证据导航、PDF、并发幂等与失败重试后再切换连接配置；密钥不进入仓库。
6. 切换验证期间保持只读或停写，失败可恢复原 SQLite；一旦 PostgreSQL 接受新写入，不能直接切回旧备份，须先处理新增数据。

上述步骤为切换时的验收要求，本轮不执行迁移、不编写迁移工具、不安装 PostgreSQL。

## 对 V1 计划的影响

- D/E 的新增模型迁移与回归在 SQLite 上验收；PostgreSQL migration executor 与并发验证移到未来切换任务。
- A/B/C/F 不因没有 PostgreSQL 环境而阻塞；六项依赖顺序不变。
- 设计中的 Evidence、provider、检索、版本隔离、发布权限与语义验收要求不降低。
- 当前运行配置和数据库无需修改。
