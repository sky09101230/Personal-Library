## Why

现有 Overview 为双语摘要与 key points，不能系统解释研究动机、缺口、方法、实验及每张主要 Figure 的论证作用，也容易漏掉长文尾部。

## What Changes

- 新增 paper_skeleton analysis type 与 personal.paper-skeleton.v1 schema。
- 消费 C 的结构化分批 context，生成论证链和逐图解读，所有重要结论校验 Evidence。
- 新增 PaperAnalysisRun 控制有界生成、幂等、缓存、force 追加、失败记录和 provenance。

## Capabilities

### New Capabilities

- `paper-skeleton-overview`: 新增有逐条 Evidence 的科研快读分析类型，覆盖论证链与主要 Figure，并保留旧 Overview 和非破坏性再生成。

### Modified Capabilities

无。保留旧 capability 的运行行为。

## Impact

新增 paper_skeleton.py、skeleton_validation.py、skeleton_views.py、skeleton_urls.py、test_paper_skeleton.py；models.py 增加 analysis type、validator 分派和 PaperAnalysisRun；新增 migration，可选独立 management command；旧 pipeline 不切换默认生成器。

## Goal / Scope / Non-goals

目标：新增有逐条 Evidence 的科研快读分析类型，覆盖论证链与主要 Figure，并保留旧 Overview 和非破坏性再生成。

范围：以上 What Changes。

非目标：不删除旧 Overview，不自动重跑 parser，不改原文摘要，不生成全库综述，不将模型总结提升为事实层。

## Dependencies

依赖 A/B/C；与 D 无业务依赖，但按 D 后 E 分配 migration，避免 models.py 并发编辑；F 负责展示。

## Migration / Compatibility

增量增加 DocumentAnalysis choice 与 PaperAnalysisRun 表/索引/约束；保留 lp_unique_analysis_input 和全部旧行。V1 使用 SQLite 完成迁移、并发和旧数据回归；PostgreSQL 实测按决策 0046 留到未来切换前，不阻塞 V1，模型不引入专属 SQL。schema 按 type 分派；禁止旧 analysis 自动转换。回滚关闭新入口并保留新增数据，旧代码只查询 overview 类型。

## Acceptance / Validation

满足本 Change spec 的全部场景和 tasks 验收。公共契约见 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)，资源上限与测试矩阵见 [preparation/17](../../../docs/preparation/17-Paper-Intelligence-V1.md)。本轮只设计，任务保持未勾选。
