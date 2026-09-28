## ADDED Requirements

### Requirement: 按用途选择模型并返回统一结果
系统 MUST 通过同一中立 provider 入口选择 chat、overview、可选 vision 模型，并返回可追踪的 provider、requested model、returned model、finish reason 和可空 usage。

#### Scenario: 分别配置模型
- **WHEN** 管理员将三个 role 配置为不同模型
- **THEN** 请求使用对应 role 的模型，业务代码不包含 DeepSeek 专属 URL 或参数

#### Scenario: 未配置视觉能力
- **WHEN** 调用方请求未配置的 vision role
- **THEN** 返回 capability_unavailable，允许业务明确采用 text_grounded 模式，不谎称已经查看图片

### Requirement: API 根路径拼接可预测
系统 MUST 将配置的 API 根路径与 chat/completions 拼接一次，不自动重复添加 v1。

#### Scenario: 本地反向代理
- **WHEN** API 根为 http://localhost:53347/v1
- **THEN** 请求路径为 /v1/chat/completions

#### Scenario: 旧 DeepSeek 根
- **WHEN** 使用原有 https://api.deepseek.com 配置
- **THEN** 保留 /chat/completions 请求路径

### Requirement: HTTP 仅允许真实 loopback
系统 MUST 默认要求 HTTPS，只对精确 localhost、127.0.0.1 及显式支持的 ::1 开放 HTTP；MUST 拒绝重定向、URL 凭据与用户驱动 endpoint。

#### Scenario: 允许本机代理
- **WHEN** localhost 解析结果为 loopback，端口合法
- **THEN** 允许 HTTP 且绕过环境 HTTP proxy

#### Scenario: 拒绝不安全配置
- **WHEN** 配置公网/局域网 HTTP、localhost.example、userinfo 或返回跳转
- **THEN** 在发送凭据前拒绝或中止请求，不跟随跳转

### Requirement: DeepSeek 配置保持完整回退
系统 MUST 在没有新 PAPER profile 时保持旧 DEEPSEEK_* 配置及 Overview prompt；新 profile 部分缺失 MUST 显式失败。

#### Scenario: 旧部署直接升级
- **WHEN** 部署仅设置旧 DeepSeek key/model
- **THEN** 旧 Overview 使用原模型与双语 schema

#### Scenario: 不完整新配置
- **WHEN** 只配置 PAPER_LLM_BASE_URL 而缺少必须模型
- **THEN** 返回 invalid_configuration，不使用旧 key 请求新 endpoint

### Requirement: 失败与资源上限统一处理
系统 MUST 限制响应体、timeout、deadline 与重试；MUST 将鉴权、限流、超时、空输出、截断及非法 completion 归一化而不返回成功分析。

#### Scenario: 瞬时失败
- **WHEN** 首次 429/5xx 或网络失败且总 deadline 仍足够
- **THEN** 最多额外尝试一次，超时后返回受控 retryable 错误

#### Scenario: 鉴权或截断
- **WHEN** 响应 401/403 或 finish_reason=length
- **THEN** 不盲目重试、不接受部分输出、不泄漏原错误 body

#### Scenario: 供应商不返回 usage
- **WHEN** 合法 completion 没有 usage
- **THEN** 返回 usage=null 并保留模型 provenance

### Requirement: 可选参数及图片不得越界
系统 MUST 仅发送 profile 声明支持的参数；vision 图片 MUST 来自受控调用方提供的有限栅格字节，禁止任意外部图片 URL。

#### Scenario: 通用兼容代理
- **WHEN** profile 不支持 thinking 或 JSON mode
- **THEN** 不发送 thinking，可省略 response_format，但业务 JSON 校验不能省略

#### Scenario: 图片超限
- **WHEN** 图片数量、字节或预算超过配置
- **THEN** 调用前返回资源错误，不向 provider 发送超限数据
