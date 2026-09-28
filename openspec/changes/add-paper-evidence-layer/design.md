# 统一论文 Evidence Layer

## Context

normalized JSON 存在 artifact，Figure 图片保存在 raw bundle 内的 segment ZIP；structure chunker 跳过空 Figure，可跨页，source_spans 才是准确定位来源。当前 uploaded/primary 过滤不等于 published。

## Decisions

1. 建立 require_published_paper(user, parse_id) 与 select_active_parse(document)。用户需登录；canonical published；upload uploaded/primary。选取规则沿用最新 succeeded parse，若没有 succeeded，允许已经持久化完整 parse/chunks 且仅 overview 阶段失败的最新 parse；running/parse/chunk 失败不选。新 parse 必须完整通过 artifact/chunk 校验，坏候选不自动串接另一 parse 的证据；返回明确 unavailable。
2. 保持当前 latest failed job 与可用 parse 分离。不同原始 upload 不可仅凭 canonical ID 混用；来源始终通过 parse.job.uploaded_document。
3. ev1:parse_id:sha256(locator) 从真实 artifact/block/span 构造。完整契约以决策 0045 第 4 节为准；同版本可重建，跨 parse 不同。缓存只存目录，授权每次重查。
4. v1 chunk 页内 offsets；v2 精确 source_spans 验证 block 文本、页、chunk/block offsets、hash。缺乏合法 structured locator 的旧 chunk 可按其完整文本/实际页范围降级为 text evidence 并标定位粒度，不能伪造 block 或 bbox。normalized artifact 损坏则 fail closed。
5. figure 独立编目，caption 是 text subtype；关联用 page+segment+format+source_index，歧义保持未关联。正文精确标签识别并保存段落 span；label 不唯一则返回歧义，不能默认匹配第一张。Table/Equation 保留文本、来源和已知结构，不让模型生成 cell 坐标。
6. raw resolver 实现于本层专用模块，只接受 parse+已验证 asset handle。outer manifest 找 segment；按 content_list 相对目录定位 asset，不能只按 basename 搜索。路径规范化后拒绝重复/越界/符号链接/不支持内容；双层压缩读取限额遵循 preparation/17。
7. validator 接受当前 parse、实际 packet allowlist、claims；检查所有 ID 属于实际送入的 excerpt locator、真实存在、同 hash/schema/parse，重查发布状态。schema 不接受模型提供的 page/URL/figure number。引用失效导致整次成功写入被拒绝；不能“删坏引用”后保留断言。
8. 本层验证来源真实性与可访问性，不实现语义判官；所有消费者仍须保守回答及显示可核查原文。

## Compatibility and Rollback

旧 Overview chunk/page validator 不强行替换；F 可为旧结果生成经原 validator 校验的只读显示适配。新目录不是旧 analysis 的数据迁移。parse 删除或取消发布后不给缓存开后门，旧会话由 D 的生命周期处理。

## Risks

MinerU 同 source_index 可跨页重复，caption 关联必须带 page。bbox 不是 OCR 准确性保证。raw bundle 过大或缺图片可只保留 caption/页导航；normalized parse 校验失败不可伪装成完整证据。

## Validation

通过合成 v1/v2、585 页分段和多图 fixtures 验证 ID 可重建、真实 span、source hash、Figure 1/10、ambiguous/missing assets；嵌套 ZIP 路径与解压预算攻击；未发布/匿名/跨 parse/未在 allowlist 的拒绝路径。

## Goals / Non-Goals

目标：将真实 parse 来源投影为四类稳定 Evidence，并提供唯一的授权、parse 选择、引用验证与安全图片读取入口。

非目标：不建 Evidence 数据表、全库索引，不修改 parser 输出/原始资料，不做科学结论生成或图片 HTTP UI。

## Dependencies and Ownership

无；C、D、E、F 必须调用本层，不得复制授权或 validator。

受影响模块：新增 evidence.py、evidence_assets.py、paper_access.py；复用 models、storage、parsers/mineru/archive；新增 test_evidence.py、test_evidence_assets.py、test_paper_access.py。HTTP 展示属于 F。

## Migration Plan

无数据库迁移；v1/v2 懒读取，旧 artifact 无需改写。ID 带版本并保留 resolver；旧版不支持必须标 unavailable，不映射到新 ID。

## Acceptance Criteria

必须通过本 Change spec 的每个场景、离线单元/回归测试和 OpenSpec strict validation；运行时与真实 provider 未测项必须分开报告。架构公共字段及版本规则遵循 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)。
