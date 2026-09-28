# Paper Intelligence V1 设计验证记录

日期：2026-09-28。审计基线：`382bcd2`。本记录仅证明设计包的结构与一致性检查，不证明功能已实现。

## 交付清单

- [整体架构、审计与依赖图](../decisions/0045-paper-intelligence-v1.md)
- [依赖准备与实施验收矩阵](17-Paper-Intelligence-V1.md)
- [A：统一 LLM provider](../../openspec/changes/unify-paper-llm-provider/proposal.md)
- [B：Evidence layer](../../openspec/changes/add-paper-evidence-layer/proposal.md)
- [C：Retrieval / context](../../openspec/changes/add-paper-retrieval-context/proposal.md)
- [D：Paper Chat](../../openspec/changes/add-evidence-grounded-paper-chat/proposal.md)
- [E：Skeleton Overview](../../openspec/changes/add-paper-skeleton-overview/proposal.md)
- [F：Reader integration](../../openspec/changes/integrate-paper-intelligence-reader/proposal.md)

每个 Change 均包含 .openspec.yaml、proposal.md、design.md、tasks.md、specs/<capability>/spec.md。总计 40 条 Requirements、94 个 Scenarios、51 个未完成实施任务。没有标记任何实现任务为完成。

## CLI 验证

本机 OpenSpec 1.13.1，使用 PowerShell 可执行的 openspec.cmd；无需初始化或更新工具层。

对以下每个 ID 执行 `openspec.cmd validate <id> --strict --no-interactive`，最终均 exit 0：

| Change | strict |
| --- | --- |
| unify-paper-llm-provider | 通过 |
| add-paper-evidence-layer | 通过 |
| add-paper-retrieval-context | 通过 |
| add-evidence-grounded-paper-chat | 通过 |
| add-paper-skeleton-overview | 通过 |
| integrate-paper-intelligence-reader | 通过 |

另执行 `openspec.cmd validate --all --strict --no-interactive`，exit 1：**30 passed, 3 failed (33 items)**。
修改前相同命令为 **24 passed, 3 failed (27 items)**。新增六项全部通过；失败项与基线一致：

| 既有 Change | 问题 |
| --- | --- |
| batch-upload-supplementary-materials | MODIFIED “Successful PDF uploads publish immediately” 缺 “New PDF upload succeeds” 与 “Exact duplicate upload succeeds” 场景 |
| organize-literature-storage-and-cli | MODIFIED “NAS WebDAV 适配器保护凭据和路径” 缺“上传对象”场景 |
| review-upload-metadata-before-commit | 上述 publication requirement 同样缺两场景，另“文件上传和元数据处理解耦”缺“元数据处理失败”场景 |

这三项为历史规范缺口，未在本轮改写；不能将全仓校验报告为通过。后续归档涉及旧能力前应单独解决，不能仅为消除错误直接复制可能与新行为冲突的旧场景。

## 跨 Change 一致性复核

| 检查项 | 设计检查结论与归属 |
| --- | --- |
| 公共基础层 | A 唯一拥有网络与配置；B 唯一拥有门禁/目录/引用验证/资产解析；C 唯一拥有排名与预算 |
| 职责重复 | D/E 共用 A/B/C；F 只作组合与安全展示。models.py 是显式共享文件，D 后 E 顺序迁移 |
| 依赖环 | A、B → C → D/E → F，无环；F 的 Evidence 直接依赖 B 已注明 |
| Evidence真实性 | 同 parse/hash/version、真实 span、实际送入模型 allowlist、发布重检；不允许由模型构造 locator |
| Figure 与资产 | 不依赖文本 chunk 包含图片；两层 ZIP 受控解析、明确无图降级和 caption/正文关联歧义 |
| 版本与旧会话 | 旧 conversation 只读，原 ID 保留原 parse 含义；生成中切换以 stale_parse 结束 |
| Migration | A/B/C/F 无 DB 迁移；D 两表；E 新 choice/run 表；旧 analysis 唯一约束保留，force nonce 追加 |
| 缓存与 provenance | 区分调用前 logical generation_key 与实际 input_fingerprint；逐调用记录 rewrite/extract/reduce/vision 来源配置 |
| LLM failure | 鉴权/限流/超时/空/截断/非法 JSON/引用非法均受控；短事务、有限 lease、迟到结果不覆盖终态 |
| 证据不足 | 固定不足说明/澄清；不以外部知识、rewrite、历史答案或中间总结冒充 Evidence |
| 长文 | 全篇 inventory、Conclusion 与尾图保底、分批有界，partial/omitted 可见 |
| 发布与用户隔离 | 新能力要求 published+uploaded+primary；会话 owner-only；取消发布后禁止新生成及旧派生结果访问 |
| 兼容 | 旧 Overview v1/v2、parse v1/v2、原 PDF Range 和原处理链保留；新 schema 独立 |
| 测试 | 每项任务包含正反场景；prep/17 列出合成数据、迁移、浏览器、语义与真实代理验收 |

发现并在最终复核中对齐的设计细节：PaperAnalysisRun 明确 request_id 字段与唯一范围；Skeleton 查询缓存不先调用模型；多模型/多批次 provenance 不只保留最终模型；vision 纳入总调用数与耗时预算。

另有已记录的历史漂移：旧 add-literature-processing-phase-1 spec 写“chunk 不跨页”，当前 structure_chunking 已合法跨页。本轮新 Evidence 明确按 span 解释，不回退当前代码；旧 Change 归档前需独立处理。

## 文档质量与范围

- 文件完整性、Markdown 本地链接存在性、task checkbox 状态检查通过。
- `git diff --check` 通过。
- 对基线文件差异核对：本轮仅新增/修改 docs 和六个 OpenSpec Change 的 Markdown/YAML。
- 没有修改 Python、模板、依赖、运行配置或数据库；没有创建 migration，没有读取/覆盖科研资料，没有调用真实 LLM，没有启动 Goal。
- 已按独立设计单元创建本地 Git 提交；本轮未请求推送，未推送这些新提交。

## 未验证与下一步

尚未执行新功能单元/集成测试、migration、真实 Cockpit/DeepSeek API、视觉推理、浏览器阅读闭环、PostgreSQL 并发或真实论文语义评测，因为本轮不实现代码。CLI strict 检查不替代上述验收。

真实 Evidence ID 只能证明来源真实与可访问，不能自动保证语义蕴含；实施验收必须逐条人工核查重要 claim。默认同步 90 秒和批次数上限是初始设计预算，长文可能只得到明确 partial 结果，不能承诺任意长度论文的一次性完整分析。

后续 Goal 建议顺序：**A → B → C → D → E → F**。每项先实现并验证所属契约，再提交；最后执行全链路及 legacy 回归。D/E 可在概念上独立，但共享 models.py 和迁移链，建议实际串行。
