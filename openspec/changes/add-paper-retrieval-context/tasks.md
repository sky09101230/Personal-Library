## 1. 检索

- [x] 1.1 实现限定 catalog 的 lexical/结构得分、稳定排序、明确 page/figure 定位。
- [x] 1.2 实现有界 query rewrite、历史指代、失败回退及候选去重/邻接扩展。

## 2. 上下文

- [x] 2.1 实现 ContextPacket v1、精确 excerpt locator、实际 allowlist、版本与 fingerprint。
- [x] 2.2 实现完整预算计算、超限错误及可观察降级；历史生成文本不能充当 Evidence。
- [x] 2.3 实现 Skeleton 全篇 inventory、保底配额、分桶/分批计划与 coverage 缺口。

## 3. 验收

- [x] 3.1 用合成中英文/指代/figure fixtures 测 Top-5 与无证据拒答路径，不依赖外网。
- [x] 3.2 用长文/尾图/极小预算测试覆盖率与实际输入不超限；完整 120 页真实样本留到 E 的集成验收。
- [x] 3.3 运行 B 证据回归、Django check、无迁移检查及本 Change strict validation。
