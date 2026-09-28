# 科研论证结构 Paper Skeleton Overview

## Context

DocumentAnalysis 已保存 parse/type/schema/provider/model/prompt/fingerprint/payload，save 执行 full_clean；唯一约束未包含 provider/model，旧 fingerprint 仅 packet。新类型应将生成配置纳入 fingerprint，避免改旧唯一键及旧行。

## Decisions

1. 新 analysis_type=paper_skeleton、schema=personal.paper-skeleton.v1、prompt=paper-skeleton-v1。clean 按 analysis_type+schema 精确分派，旧 overview v1/v2 继续原 validator；未知新 schema 拒绝写入。原 pipeline 继续旧 Overview，不在解析事务中调用 Skeleton。
2. payload 含 language、sections、figures、limitations、coverage。sections 固定 introduction/motivation/gap/proposed_idea/method/experiments/results/conclusion；每项为 supported claims[] 或 insufficient_evidence。没有材料不能套模板编造 Gap、实验或“证明”。
3. 每张结构上发现的 Figure 在 coverage inventory 有记录；主要图默认指主 PDF 中可识别图，不按文首数量截掉后图。figure 条目包含 ID、验证问题、设置、结果和论证作用，这些字段均为 claim 数组或缺证状态，不能只有 caption 摘抄却宣称解释完成。标签由 B 派生，模型不造图号。
4. V1 默认为中文（可选英文），与旧 Overview 的双语 schema 独立。text_grounded 明示仅解释 caption/正文；vision_assisted 仅在配置模型、图片可安全读取且预算可算时启用。图片读取失败继续文字模式并记录降级，不能声称读过图中像素。
5. C 先给有限分批计划。每个 extract 输出 claims+原始 Evidence ID，经 B 校验；reducer 同时拿选中 claims 与它们对应原始 excerpt 和 allowlist。中间 LLM 文本不是 Evidence，最终 B 再验真实引用。最多四 extract+一 reduce，90 秒总 deadline 包括重试；超限 fail 或明确 partial，coverage 不得被 reducer 改为 complete。
6. PaperAnalysisRun 字段遵循 0045：parse/requested_by/type/generation_key/nonce/request_id/status/result/provenance/context/error/timestamps/lease。request_id 按 requested_by+request_id 唯一，同 parse/type 最多一个 pending；相同请求幂等，不同用户同 key 可共享已发布 analysis 但不共享私有运行详情。
7. generation_key 包括 parse+artifact+chunk manifest、C 的确定性输入计划、B/C/prompt/schema 版本、provider profile/API 根摘要、requested model/参数、language、vision 模式。普通请求按 key 找最新成功 run.result；force 生成 nonce。input_fingerprint 对完整实际输入与生成配置加 nonce 取 SHA，原唯一键可保留。
8. 输入计划形成后短事务 claim run，LLM 在事务外；deadline/lease、busy 和迟到条件更新与 D 采用相同规则，但本 Change 不重新定义通用 transport/retrieval。GET 不生成；POST 默认查缓存，force 必须显式 POST。失败不会更新 latest successful 选择。
9. 保存前检查仍 published、parse 仍 active（切换则 stale_parse，不写成功结果）、所有 claims 有合法原文 ID；运行失败只落 run 错误，不标解析 job failed。批次来源清单/覆盖率保存在 analysis payload 与 run context_manifest，raw LLM 响应不留未验证可见副本。
10. context_manifest 按调用保存 extract/reduce/vision 的 purpose、provider、requested/returned model、prompt、输入哈希、实际 allowlist 和可空 usage；顶层 model 代表最终组织模型。vision 也占最多五次总调用额度，不能在分批调用外无限追加。generation_key 只含调用前确定的计划与配置；实际 fingerprint 额外记录已执行输入和 nonce，避免查缓存前先调用模型。

## Cache / Regeneration / Compatibility

旧 fingerprint 和 overview 数据不回填。model/prompt/context/vision/language 配置任一变化使新逻辑 key 变化；model 别名实际变动无法自动发现，force 负责显式更新。force 成功追加 analysis；force 失败仍显示旧成功。原有 unique constraint 的并发冲突在短事务处理并复用已存在等价结果，不能覆盖数据。

## Risks

图多、论文长或模型慢时 90 秒不保证全文生成；partial coverage 是明确产品状态，保留每个 omitted figure/section 的原因。图像解释也不能证明科学结论，人工验收必须检查 claim 支持度。共享 Skeleton 为 published 论文派生阅读内容，不能泄漏请求者私有聊天（生成输入不含 Chat 历史）。

## Validation

合成论文覆盖完整论证链、无实验/无 Gap、末页 conclusion、无 caption、表格/公式、更多图超批次、无 vision 与有 vision；严格校验中间与最终 Evidence。迁移测试旧 Overview v1/v2、原始摘要 hash、缓存/force/并发/超时/撤销发布/重 parse 与失败保旧。

## Goals / Non-Goals

目标：新增有逐条 Evidence 的科研快读分析类型，覆盖论证链与主要 Figure，并保留旧 Overview 和非破坏性再生成。

非目标：不删除旧 Overview，不自动重跑 parser，不改原文摘要，不生成全库综述，不将模型总结提升为事实层。

## Dependencies and Ownership

依赖 A/B/C；与 D 无业务依赖，但按 D 后 E 分配 migration，避免 models.py 并发编辑；F 负责展示。

受影响模块：新增 paper_skeleton.py、skeleton_validation.py、skeleton_views.py、skeleton_urls.py、test_paper_skeleton.py；models.py 增加 analysis type、validator 分派和 PaperAnalysisRun；新增 migration，可选独立 management command；旧 pipeline 不切换默认生成器。

## Migration Plan

增量增加 DocumentAnalysis choice 与 PaperAnalysisRun 表/索引/约束；保留 lp_unique_analysis_input 和全部旧行。schema 按 type 分派；禁止旧 analysis 自动转换。回滚关闭新入口并保留新增数据，旧代码只查询 overview 类型。

## Acceptance Criteria

必须通过本 Change 全部 spec 场景、对应测试和 strict validation。真实 provider、PostgreSQL 和语义评测未验证项单独报告；本轮不实施。公共契约遵循 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)。
