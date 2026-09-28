## Why

已有 chunk/page 引用无法涵盖无文本 Figure、精确跨页 span 与表格公式；旧校验也不能阻止引用同 parse 中本轮未提供的片段。

## What Changes

- 只读投影 normalized parse、chunks 和 raw bundle；统一 EvidenceCatalog/locator/schema。
- 建立 published+primary+uploaded 门禁及 active parse 选择契约。
- 建立 Figure-caption-正文关联、受控 asset resolver 与 claim 引用 validator。

## Capabilities

### New Capabilities

- `paper-evidence`: 将真实 parse 来源投影为四类稳定 Evidence，并提供唯一的授权、parse 选择、引用验证与安全图片读取入口。

### Modified Capabilities

无。旧 capability 的历史规范不在本 Change 重写。

## Impact

新增 evidence.py、evidence_assets.py、paper_access.py；复用 models、storage、parsers/mineru/archive；新增 test_evidence.py、test_evidence_assets.py、test_paper_access.py。HTTP 展示属于 F。

## Goal / Scope / Non-goals

目标：将真实 parse 来源投影为四类稳定 Evidence，并提供唯一的授权、parse 选择、引用验证与安全图片读取入口。

范围：以上 What Changes。

非目标：不建 Evidence 数据表、全库索引，不修改 parser 输出/原始资料，不做科学结论生成或图片 HTTP UI。

## Dependencies

无；C、D、E、F 必须调用本层，不得复制授权或 validator。

## Migration / Compatibility

无数据库迁移；v1/v2 懒读取，旧 artifact 无需改写。ID 带版本并保留 resolver；旧版不支持必须标 unavailable，不映射到新 ID。

## Acceptance / Validation

以 specs/paper-evidence/spec.md 的全部场景及 tasks.md 验收项为准。公共契约见 [架构决策](../../../docs/decisions/0045-paper-intelligence-v1.md)，测试矩阵与资源上限见 [实施准备](../../../docs/preparation/17-Paper-Intelligence-V1.md)。本阶段只设计，所有实现任务保持未勾选。
