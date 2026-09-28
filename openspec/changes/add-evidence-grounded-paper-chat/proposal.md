## Why

项目没有绑定用户与 parse 的多轮论文问答；简单调用 LLM 无法保证证据真实、历史不污染、重解析与并发提交安全。

## What Changes

- 新增 conversation/message 数据模型、幂等 turn、有限历史与生命周期。
- 调用 A/B/C 生成并校验 claim-based 回答，支持明确证据不足及澄清。
- 提供登录/CSRF 保护的 JSON 服务入口，供 F 接入阅读器。

## Capabilities

### New Capabilities

- `evidence-grounded-paper-chat`: 提供仅依据当前论文真实 Evidence 的多轮私有会话，成功回答必须通过公共引用校验并完整持久化 provenance。

### Modified Capabilities

无。保留旧 capability 的运行行为。

## Impact

models.py 新增 PaperConversation/PaperChatMessage；新增 paper_chat.py、chat_views.py、chat_urls.py、test_paper_chat.py、test_chat_views.py 和增量 migrations；最终项目路由组合由 F。

## Goal / Scope / Non-goals

目标：提供仅依据当前论文真实 Evidence 的多轮私有会话，成功回答必须通过公共引用校验并完整持久化 provenance。

范围：以上 What Changes。

非目标：不做跨论文 memory、SSE token 流、外网工具、MCP Chat、分享会话或后台复杂任务编排。

## Dependencies

依赖 A unify-paper-llm-provider、B add-paper-evidence-layer、C add-paper-retrieval-context；UI 由 F；迁移先于 E 顺序生成。

## Migration / Compatibility

新增两表和外键/唯一约束；旧表无回填。SQLite/PostgreSQL 升级保留现有 parse/analysis；user/parse/conversation 删除 CASCADE 消息，遵循已有 upload 删除关系。回滚先禁用入口并保留表。

## Acceptance / Validation

满足本 Change spec 的全部场景和 tasks 验收。公共契约见 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)，资源上限与测试矩阵见 [preparation/17](../../../docs/preparation/17-Paper-Intelligence-V1.md)。本轮只设计，任务保持未勾选。
