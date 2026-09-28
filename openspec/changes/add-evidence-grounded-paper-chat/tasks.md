## 1. 模型与迁移

- [ ] 1.1 新增 conversation/message 模型及字段，配置删除关系、幂等/sequence/单 pending 唯一约束。
- [ ] 1.2 编写增量 migration，使用 MigrationExecutor 验证 SQLite/PostgreSQL 原 parse 与 analysis 不变。

## 2. 会话服务

- [ ] 2.1 实现 owner/published/active parse 校验与分页读取、CSRF JSON POST，不信任客户端 user/role/provider。
- [ ] 2.2 实现短事务 claim、deadline/lease、幂等/busy/过期/迟到结果处理与安全错误。

## 3. 生成

- [ ] 3.1 接入 A/B/C，多轮历史只辅助指代；结构 claims 通过公共 validator 后原子保存 answer/provenance。
- [ ] 3.2 实现 insufficient/clarification、重 parse 只读、撤销发布和删除行为。

## 4. 验收

- [ ] 4.1 测试多用户、多轮中文、历史污染、伪造/跨 parse/未入包引用、prompt injection、网络/JSON 失败。
- [ ] 4.2 测试并发、重复、lease、删除和切换；回归旧 parsing/overview 与 MCP 发布边界。
- [ ] 4.3 执行 Django check、迁移一致性、本 Change strict validation；明确真实模型语义评测未测项。
