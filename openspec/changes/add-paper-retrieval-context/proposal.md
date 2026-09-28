## Why

当前 Overview 从头截断，无法保证 Conclusion 与尾部 Figure；现有系统缺少单篇问答检索和中文问题到英文正文的召回。

## What Changes

- 单篇 lexical 排名、结构加权、邻接扩展和去重。
- 受限 query rewrite 与指代消解，失败可观察。
- Chat packet 和 Skeleton 分桶/分批 context，完整预算、coverage 与 fingerprint。

## Capabilities

### New Capabilities

- `paper-retrieval-context`: 提供统一、有预算、可追踪的 ContextPacket，支持多语言单篇检索与结构覆盖，不引入向量服务。

### Modified Capabilities

无。保留旧 capability 的运行行为。

## Impact

新增 apps/literature_processing/retrieval.py、paper_context.py；测试 test_paper_retrieval.py、test_paper_context.py；不修改旧 build_overview_packet。

## Goal / Scope / Non-goals

目标：提供统一、有预算、可追踪的 ContextPacket，支持多语言单篇检索与结构覆盖，不引入向量服务。

范围：以上 What Changes。

非目标：不做全库搜索、embedding 服务、科学回答、持久会话、analysis 保存或 UI。

## Dependencies

依赖 unify-paper-llm-provider（A）与 add-paper-evidence-layer（B）；D/E 只消费本层 packet。

## Migration / Compatibility

无数据库迁移或批量索引；从 B 的单篇目录按需构建。版本进入 packet/fingerprint；后续 ranking 升级不改变 Evidence ID 的语义。

## Acceptance / Validation

满足本 Change spec 的全部场景和 tasks 验收。公共契约见 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)，资源上限与测试矩阵见 [preparation/17](../../../docs/preparation/17-Paper-Intelligence-V1.md)。本轮只设计，任务保持未勾选。
