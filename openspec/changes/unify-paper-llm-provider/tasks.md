## 1. 契约与配置

- [ ] 1.1 实现 llm.py 中立请求/结果/error 和三 role 配置，记录 profile provenance。
- [ ] 1.2 实现 API 根拼接与完整 DeepSeek 回退、可选 JSON/vision 能力。

## 2. 传输与兼容

- [ ] 2.1 实现 loopback/HTTPS 校验、禁止跳转、proxy 例外、响应限额和总 deadline。
- [ ] 2.2 实现有界重试与错误脱敏；旧 overview_provider 保留 prompt、接口及返回字段并使用兼容包装。

## 3. 验收

- [ ] 3.1 新增 test_llm：路径/URL 攻击/能力/缺配置/401/429/5xx/timeout/空/截断/无 usage/泄密断言。
- [ ] 3.2 运行旧 test_overview、Django check、makemigrations --check --dry-run 和本 Change strict validation。
- [ ] 3.3 以合成输入执行本机代理 smoke，记录实际支持能力；无服务时明确标未验证，不勾选此项。
