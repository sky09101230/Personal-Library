## 1. 兼容模型

- [x] 1.1 增加 paper_skeleton choice/schema 分派与 PaperAnalysisRun 模型、request_id/generation_key/nonce/lease/约束。
- [x] 1.2 编写 D 之后的增量 migration，验证旧 Overview 行、原 PDF 和 metadata 不变。

## 2. 生成与校验

- [x] 2.1 实现固定 sections/figures/limitations/coverage schema 与逐 claim 引用校验。
- [x] 2.2 消费 C 的结构 context，实现引用校验和原始 Evidence allowlist，限制输入预算。
- [x] 2.3 实现 text_grounded/vision_assisted 显式模式与缺图/缺材料/超预算状态；vision 具体图像批次留到后续增强。

## 3. 运行与缓存

- [x] 3.1 实现逻辑缓存 key、实际 input fingerprint、request_id 幂等、force nonce 追加及失败保留旧结果。
- [x] 3.2 提供显式 POST 服务及状态读取，短事务 claim/终态写入，重查 published/active parse。

## 4. 验收

- [x] 4.1 测试论证链、缺材料、幻觉引用和 provider 失败；真实长文/逐图语义留到最终 E2E。
- [x] 4.2 测试缓存、force、重 parse 兼容；回归旧 Overview/pipeline/view。
- [x] 4.3 运行 Django check、SQLite migration executor、strict validation；完成授权样本语义验收后才标功能完成。PostgreSQL 实测按决策 0046 移至未来切换任务，不阻塞 V1。
