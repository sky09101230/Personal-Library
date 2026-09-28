## 1. 兼容模型

- [ ] 1.1 增加 paper_skeleton choice/schema 分派与 PaperAnalysisRun 模型、request_id/generation_key/nonce/lease/约束。
- [ ] 1.2 编写 D 之后的增量 migration，验证旧 Overview 行、原 PDF 和 metadata 不变。

## 2. 生成与校验

- [ ] 2.1 实现固定 sections/figures/limitations/coverage schema 与逐 claim 引用校验。
- [ ] 2.2 消费 C 的批次计划，实现 extract/reduce 双校验和原始 Evidence 重附，限制调用总量/deadline。
- [ ] 2.3 实现 text_grounded/vision_assisted 显式模式与缺图/缺材料/超预算状态。

## 3. 运行与缓存

- [ ] 3.1 实现逻辑缓存 key、实际 input fingerprint、request_id 幂等、force nonce 追加及失败保留旧结果。
- [ ] 3.2 提供显式 POST 服务及状态读取，短事务 claim/终态写入，重查 published/active parse。

## 4. 验收

- [ ] 4.1 测试论证链、每图作用、末页/尾图、缺实验/图、幻觉引用、批次遗漏和 provider 失败。
- [ ] 4.2 测试缓存与参数变化、force、并发/lease、重 parse/撤销发布；回归旧 Overview/pipeline/view。
- [ ] 4.3 运行 Django check、SQLite migration executor、strict validation；完成授权样本语义验收后才标功能完成。PostgreSQL 实测按决策 0046 移至未来切换任务，不阻塞 V1。
