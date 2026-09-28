## Why

当前 Overview 将配置、HTTP、DeepSeek 参数、prompt 与 JSON 解析绑定，无法直接使用本机 OpenAI-compatible 代理，也无法分别选择 chat/overview/vision 模型。

## What Changes

- 新增三个模型 role 与统一 provider 配置、请求/响应/错误契约。
- 将旧 Overview 的 HTTP transport 接入兼容包装，保留业务 prompt 和 payload validator。
- 支持精确 loopback HTTP 例外、显式能力开关和配置来源记录。

## Capabilities

### New Capabilities

- `paper-llm-provider`: 以一个中立、有界、安全的 chat-completions transport 支撑论文智能能力，并保持旧 DeepSeek Overview 行为。

### Modified Capabilities

无。旧 capability 的历史规范不在本 Change 重写。

## Impact

新增 apps/literature_processing/llm.py；调整 overview_provider.py 的 transport 包装；测试 test_llm.py 与旧 test_overview.py；.env.example、README 仅在实施阶段更新。

## Goal / Scope / Non-goals

目标：以一个中立、有界、安全的 chat-completions transport 支撑论文智能能力，并保持旧 DeepSeek Overview 行为。

范围：以上 What Changes。

非目标：不迁移 skills/ai_enrichment 或 box_upload/ai_metadata，不做多供应商自动路由、Agent SDK、Evidence、检索或新 UI。

## Dependencies

无；B 可独立设计，C/D/E 消费本 Change。

## Migration / Compatibility

无数据库迁移；旧 DEEPSEEK_* 只在无 PAPER profile 时完整回退；不改旧 analysis 行或其 fingerprint。回滚恢复旧 provider wrapper 即可。

## Acceptance / Validation

以 specs/paper-llm-provider/spec.md 的全部场景及 tasks.md 验收项为准。公共契约见 [架构决策](../../../docs/decisions/0045-paper-intelligence-v1.md)，测试矩阵与资源上限见 [实施准备](../../../docs/preparation/17-Paper-Intelligence-V1.md)。本阶段只设计，所有实现任务保持未勾选。
