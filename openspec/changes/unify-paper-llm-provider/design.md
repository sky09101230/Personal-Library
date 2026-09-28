# 统一论文 LLM Provider

## Context

overview_provider.py 当前向 base_url/chat/completions 发送 DeepSeek thinking 参数并要求 HTTPS；response_format、prompt 与业务结构混合。复用 urllib 和现有注入 request_func 测试手法，无新依赖。

## Decisions

1. 提供 complete(role, messages, output_mode, budget, images=None) 和不可变结果/安全异常。transport 只解析 completion envelope；Chat/Skeleton 自己校验业务 JSON，禁止其直接请求网络。
2. PAPER_LLM_BASE_URL 定义为 API 根，PAPER_CHAT_MODEL、PAPER_OVERVIEW_MODEL 分开必填，PAPER_VISION_MODEL 可空；全新 profile 必须配置完整，不能与旧密钥混用。所有默认值与向后映射集中在本模块。
3. DeepSeek wrapper 保留 generate_deepseek_overview(packet) 函数和旧 prompt/返回结构，兼容 profile 才附加 thinking；新 profile 仅发送其声明支持的参数。JSON mode 可配置，不支持时输出 JSON 文本并在业务层严格解析；vision 缺失不隐式启用。
4. URL 解析后要求 https 或精确 loopback http；localhost 实际解析到 loopback 才允许，拒绝重定向与 userinfo/query/fragment，loopback 禁用环境代理，HTTPS 保持证书校验。地址由管理员配置，永远不接受问题或模型生成的 endpoint。
5. 返回 requested_model 与 returned_model、provider profile、finish_reason、usage，可缺 usage 不视为失败。模型输出 length、空、错误结构不当作成功。
6. 网络最多两次尝试，总调用 deadline 内有界退避；401/403 不重试，429/5xx/transport 可重试一次。响应 2 MiB 上限。调用方剩余 deadline 传入，多个批次不能各自绕开总耗时预算。
7. API key、原始 Authorization、供应商原始错误 body 不进入异常、日志、DB。loopback 无 key 可不发送 Authorization，远程缺 key disabled。profile 指纹不包含 key。

## Compatibility and Rollback

旧 Overview schema、英文后中文 prompt、错误码调用兼容、旧返回 provider=deepseek 保持。新 profile 配置失败不能悄悄退到 DeepSeek；既有模型元数据不回填。关闭新 profile 即恢复完整旧配置路径。

## Risks

2026-09-28 已通过原始 HTTP 对本机 Cockpit 的 gpt-6-luna 验证文本、JSON mode 与合成图片，认证配置来自未提交的 .env；三项均 HTTP 200、finish_reason=stop。该环境证据不代表本 Change 中尚未实现的 transport、安全校验和错误处理已完成，实施后须经新入口复验。其它模型与完整输入窗口仍按实际配置验证。重试可能重复计费，限制尝试且不把部分输出存为成功。HTTPS 私有服务如需访问由管理员配置，不开放用户驱动 URL。

## Validation

离线 mock HTTP 覆盖不同 profile、路径拼接、安全与失败矩阵；旧 Overview 测试回归；部署后用合成问题验证 localhost:53347/v1 的实际模型配置，日志不得含 key。

## Goals / Non-Goals

目标：以一个中立、有界、安全的 chat-completions transport 支撑论文智能能力，并保持旧 DeepSeek Overview 行为。

非目标：不迁移 skills/ai_enrichment 或 box_upload/ai_metadata，不做多供应商自动路由、Agent SDK、Evidence、检索或新 UI。

## Dependencies and Ownership

无；B 可独立设计，C/D/E 消费本 Change。

受影响模块：新增 apps/literature_processing/llm.py；调整 overview_provider.py 的 transport 包装；测试 test_llm.py 与旧 test_overview.py；.env.example、README 仅在实施阶段更新。

## Migration Plan

无数据库迁移；旧 DEEPSEEK_* 只在无 PAPER profile 时完整回退；不改旧 analysis 行或其 fingerprint。回滚恢复旧 provider wrapper 即可。

## Acceptance Criteria

必须通过本 Change spec 的每个场景、离线单元/回归测试和 OpenSpec strict validation；运行时与真实 provider 未测项必须分开报告。架构公共字段及版本规则遵循 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)。
