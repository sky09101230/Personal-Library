## Why

现有详情只显示旧 Overview、parse 元信息和 chunks，新能力需要一致的来源入口，否则用户无法验证回答或判断当前结果使用了哪份 parse。

## What Changes

- 四区阅读布局与解析版本、生成状态及旧 Overview 回退。
- 公共 Evidence chip/source panel、受控 figure asset HTTP 接口。
- 接入 D/E 服务并完成授权、CSRF、XSS、导航及旧 PDF/Overview 回归。

## Capabilities

### New Capabilities

- `paper-intelligence-reader`: 在现有 Django 详情页组合 Overview、Chat、Parsed Content、PDF，并让所有 Evidence 能回到同一版本真实来源。

### Modified Capabilities

无。保留旧 capability 的运行行为。

## Impact

apps/literature_processing/views.py/urls.py、templates/literature_processing/detail.html、新 _paper_evidence.html 及局部静态样式/脚本；组合 chat_urls/skeleton_urls；新增 reader_views.py 或 evidence 视图及 test_paper_reader.py；复用 apps/box_upload PDF stream。

## Goal / Scope / Non-goals

目标：在现有 Django 详情页组合 Overview、Chat、Parsed Content、PDF，并让所有 Evidence 能回到同一版本真实来源。

范围：以上 What Changes。

非目标：不实现新的 PDF.js/bbox 标注器，不创建 SPA，不重新实现 provider/retrieval/validator，不公开原始存储目录或新增 MCP 工具。

## Dependencies

依赖 A/B/C/D/E；直接消费 B 的来源、D 的对话服务与 E 的分析服务，作为最后一个集成 Change。

## Migration / Compatibility

无数据库迁移；新功能开关可关闭，原 PDF/旧 Overview 路径保留。无新结果时可读旧版本；旧 evidence 只作安全显示适配，不写回旧 payload。回滚关闭新入口并保留 Chat/Skeleton 数据。

## Acceptance / Validation

满足本 Change spec 的全部场景和 tasks 验收。公共契约见 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)，资源上限与测试矩阵见 [preparation/17](../../../docs/preparation/17-Paper-Intelligence-V1.md)。本轮只设计，任务保持未勾选。
