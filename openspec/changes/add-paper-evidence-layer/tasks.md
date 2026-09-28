## 1. 目录与访问

- [x] 1.1 实现 published/primary/uploaded 门禁和 active parse 选择规则；覆盖仅 overview 失败的完整 parse。
- [x] 1.2 实现 v1/v2 EvidenceCatalog、确定性 locator、span/hash/version 校验与有界缓存。

## 2. 结构与图片

- [x] 2.1 建立 Figure-caption-mention 保守关联与 table/equation 投影。
- [x] 2.2 实现 raw manifest/segment/content-list 相对路径 resolver、安全栅格读取与两层资源限额。

## 3. 校验边界

- [x] 3.1 实现 claim schema、实际 packet allowlist 和来源/权限重检，不复制旧 Overview 语义。
- [x] 3.2 定义 unavailable/ambiguous/degraded 状态和 parse 删除后的行为。

## 4. 验收

- [x] 4.1 添加 v1/v2、跨页、585 页、无文本图、图号歧义、缺图、ZIP 攻击、未发布与伪引用测试。
- [x] 4.2 回归 test_parsing/test_mineru_adapter/test_models；Django check、无迁移检查、本 Change strict validation。
