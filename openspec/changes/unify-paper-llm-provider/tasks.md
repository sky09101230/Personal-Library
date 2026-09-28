## 1. 契约与配置

- [x] 1.1 实现 llm.py 中立请求/结果/error 和三 role 配置，记录 profile provenance。
- [x] 1.2 实现 API 根拼接与完整 DeepSeek 回退、可选 JSON/vision 能力。

## 2. 传输与兼容

- [x] 2.1 实现 loopback/HTTPS 校验、禁止跳转、proxy 例外、响应限额和总 deadline。
- [x] 2.2 实现有界重试与错误脱敏；旧 overview_provider 保留 prompt、接口及返回字段并使用兼容包装。

## 3. 验收

- [x] 3.1 新增 test_llm：路径/URL 攻击/能力/缺配置/401/429/5xx/timeout/空/截断/无 usage/泄密断言。
- [x] 3.2 运行旧 test_overview、Django check、makemigrations --check --dry-run 和本 Change strict validation。
- [x] 3.3 通过新 provider 入口以合成输入复验本机代理 smoke；文本、JSON 和 vision 均通过。该 smoke 不替代论文语义验收。
