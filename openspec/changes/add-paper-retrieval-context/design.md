# 单篇论文 Retrieval 与 Context Builder

## Context

现有 LiteratureChunk 含 section_path/source_spans，但旧 Overview 只取前 80,000 字符。B 提供结构来源与鉴权；本层不能自己放宽 published 或 parse 限制。

## Decisions

1. retrieve(catalog, query, history, budget) 返回候选 Evidence locator、分项得分、原始/改写查询及 warnings。V1 用 Python 词项计分和长度归一化，加 heading/section/caption/明确 page/figure 加权；按 source order 稳定 tie-break。未来 BM25/embedding 仅替换候选排名策略。
2. 中文/英文 query 原文始终保留；最多调用一次 A 的 chat role 生成最多四个检索表达。输入仅当前问题、有限历史与该论文术语；不能把 rewrite 作为知识来源。Fig. 2、公式编号、单位和用户否定条件需保留，存在指代歧义则返回 clarification_required。
3. rewrite 失败执行原词与可用论文术语召回，标 rewrite_unavailable；不是“翻译一定可用”。无候选返回 insufficient_retrieval，D 不能以外部常识回答。失败场景不把相似但无关段落硬排为证据。
4. 多路 lexical/结构候选合并，重叠 span 去重；邻接最多前后各一段、保留 section 边界。Caption 命中带出 figure 与明确 mention，Figure 直接问题优先图的 caption/mention；未发送图片时 mode=text_grounded。
5. ContextPacket 字段及 ID 规则服从 0045。实际截取片段经 B 生成对应 locator，不可使用整 chunk ID 声称模型看过全部。history 不是 evidence，旧引用重用需重新取真实原文。最终 allowlist 只来自真正序列化发送的 items。
6. budget = 配置 context window - 输出预留 - prompt/history/JSON/图片 - 10% margin。无 tokenizer 时完整输入 UTF-8 字节作保守文本上界并标 estimated，无法预算的图像禁用。小预算先取消可选 rewrite/邻接，仍不足返回 context_budget_exceeded。
7. Skeleton 先扫全篇 inventory，桶为 abstract、introduction、method、results、conclusion、figures；存在的 Conclusion 保留至少一处真实 span，每个 figure 先有 inventory/可用状态。caption/mention 分批覆盖尾部 Figure。没有章节标题使用有标记的推断桶，不伪造源 heading。
8. 默认文本预算分配为 abstract 10%、introduction 15%、method 20%、results 20%、conclusion 15%、figures 20%；缺桶释放预算，非空桶保底先于比例。过长单项生成局部 locator；无法放入 Conclusion/尾部 Figure 保底则显式不足，不从前至后盲截。
9. 输出 section/figure 批次计划，最多四个 extract packet，另预留一次 reducer。无法处理全部 inventory 时给 selected/omitted/reason，E 负责执行并记录 partial。C 不运行科学总结、不把提炼文字伪装为新证据。

## Compatibility and Risks

旧 Overview 仍用旧 packet；新 Schema 为 personal.paper-context.v1。lexical 对同义和跨语言不保证召回，需合成/授权评测检验。chunk 扫描内存有界，超大单篇可分批扫描，不引入全库缓存。缓存 key 绑定 parse/hash/query/versions 与预算，不缓存权限。

## Validation

中文“为什么使用非相干光”在 mock rewrite 后应使含 incoherent illumination 的预定段落进入 Top-5；原词/英文/缩略词/前轮指代/明确 Figure/page 均有 fixture。长文末页 conclusion、最后 figure 与预算不足必须有确定性断言，覆盖率不能只统计入包内容而漏掉总 inventory。

## Goals / Non-Goals

目标：提供统一、有预算、可追踪的 ContextPacket，支持多语言单篇检索与结构覆盖，不引入向量服务。

非目标：不做全库搜索、embedding 服务、科学回答、持久会话、analysis 保存或 UI。

## Dependencies and Ownership

依赖 unify-paper-llm-provider（A）与 add-paper-evidence-layer（B）；D/E 只消费本层 packet。

受影响模块：新增 apps/literature_processing/retrieval.py、paper_context.py；测试 test_paper_retrieval.py、test_paper_context.py；不修改旧 build_overview_packet。

## Migration Plan

无数据库迁移或批量索引；从 B 的单篇目录按需构建。版本进入 packet/fingerprint；后续 ranking 升级不改变 Evidence ID 的语义。

## Acceptance Criteria

必须通过本 Change 全部 spec 场景、对应测试和 strict validation。真实 provider、PostgreSQL 和语义评测未验证项单独报告；本轮不实施。公共契约遵循 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)。
