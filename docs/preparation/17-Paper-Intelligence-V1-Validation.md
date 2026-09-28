# Paper Intelligence V1 设计验证记录

日期：2026-09-28。审计基线：`382bcd2`。本记录包含设计、实现和验证状态；未通过的真实 Skeleton 长输入与浏览器视觉闭环不会被标记为完成。

## 当前状态（历史清理与环境复核后）

全仓 OpenSpec strict 已 **33 通过、0 失败**；下文首次交付的 30/3 是保留的历史记录，不是当前状态。历史修复提交为 db893be（场景继承）与 a0b9499（跨页 chunk 规范）。

六个 Change 已按 A→F 串行实现并分别提交：A `ac5634b`、B `1437ef7`、C `c585514`、D `a7053e1`、E `572cfb7`、F `9d0c3fd`；后续 AI 修复为 `1ee9816`、`067833c`。D/E 使用 SQLite migrations 0004、0005、0006。

| 当前可验证项 | 结果 |
| --- | --- |
| 三个历史 Change 的场景继承 | 修复并 strict 通过；保留原场景名称，按当前条件修订，明确 batch 先于 review 归档 |
| v1/v2 chunk 规范 | spec/design 已区分页内与跨页；临时合成两页测试验证 source_spans 的 page 和 offsets 精确 |
| Django check | 通过，无问题 |
| makemigrations --check --dry-run | 通过，No changes detected |
| migrate --check | 通过，无待应用迁移；未执行生产迁移 |
| 全量现有测试 | 385 项，378 通过、7 跳过，0 失败；111.884 秒 |
| 跳过原因 | 7 项均为既有 NJU Box backend retired，不是新功能测试被跳过 |
| Cockpit 连通与认证 | localhost:53347 端口可达；无认证 /models=401，.env 配置 Bearer 后 /models=200 |
| 文本 smoke | gpt-6-luna，HTTP 200，stop，精确 PROBE_OK，usage 存在，4.79 秒 |
| JSON smoke | gpt-6-luna，HTTP 200，stop，合法 JSON 且保持合成 evidence ID，4.83 秒 |
| Vision smoke | gpt-6-luna，HTTP 200，stop，正确识别临时 PNG 左红右蓝，4.63 秒 |

API smoke 使用 /v1/chat/completions、temperature=0、max_tokens=256；JSON 和 vision 请求启用 response_format=json_object，vision 为内存合成 PNG 的 data URL。测试未发送论文或真实实验内容，未输出/保存 API key；.env 被 Git 忽略。gpt-6-luna 来自实际 /models 返回，不是猜测模型名；它只是本次 smoke 选择，不自动成为三个业务 role 的默认配置。

完整 Django 测试沿用项目 .venv，通过仅测试进程的 MINERU_REALTIME_API_TOKEN=" " 隔离本机专用 token；不修改真实 .env。Windows 子进程空字符串可能移除变量，使 settings 从 .env 再次装载真实 token，因此用空白字符串让业务 strip 后为空。此前唯一环境相关失败已在本次完整回归中消除，非仅单项补测。

## 剩余验收项的准确分类

| 项目 | 当前状态 | 完成条件 |
| --- | --- | --- |
| PostgreSQL 现有/新增迁移与并发 | 按用户要求移至未来切换任务，不是 SQLite V1 阻塞项；当前环境未提供 | 切换前按决策 0046 提供测试实例并完成数据搬迁、并发及回退验收 |
| 新统一 provider 安全/错误处理 | 已实现并通过 16 项 Provider/Overview 测试及真实文本/JSON/vision smoke | 后续按完整模型窗口和其它模型继续复验 |
| 完整输入窗口/其它模型 | 本次小输入 smoke 未验证 | 选定 profile 的模型与窗口配置，验证预算、超限和输出行为 |
| Chat/Skeleton migration、Evidence validator、跨语言 retrieval | 已实现；SQLite migrations 和 25 项相关测试通过 | 继续做更多真实论文/浏览器验证 |
| 新阅读器浏览器闭环 | API/template 已实现；未启动浏览器服务做视觉/键盘复核 | 启动测试环境后验证证据、图、caption、chunk/PDF 导航 |
| 真实论文 Paper Chat | 已通过 parse 14（11 页、219 Evidence）：3 claims、7 Evidence 引用并持久化 | 增加人工问题和浏览器点击验收 |
| 真实论文 Skeleton | Cockpit 对完整 Skeleton prompt 多次 transport timeout，已安全记录失败，未伪造成功 | 调整代理输入/模型窗口或换可用模型后重新执行 |

上表属于后续切换条件或实施后验收，不再笼统列作“已存在但未检查的历史问题”。按 [0046](../decisions/0046-paper-intelligence-sqlite-first.md)，V1 使用现有 SQLite，PostgreSQL 未实测不阻塞 V1；不将延期项标为通过。

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

## 首次设计交付的 CLI 验证（历史记录）

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

首次设计交付保留了上述三个历史规范缺口；随后按用户要求已修复，当前全仓 33/33 通过。修复保留了“确认后发布”、暂存失败可重试和 namespace 接口兼容，没有直接复制会恢复旧发布语义的场景内容。

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

首次设计交付记录的“chunk 不跨页”漂移已在后续清理中修复：旧 Change 的 spec/design 现在明确 v1 页内、v2 结构跨页并逐段溯源；未改动运行代码。

## 首次设计交付的文档质量与范围（历史记录）

- 文件完整性、Markdown 本地链接存在性、task checkbox 状态检查通过。
- `git diff --check` 通过。
- 对基线文件差异核对：本轮仅新增/修改 docs 和六个 OpenSpec Change 的 Markdown/YAML。
- 没有修改 Python、模板、依赖、运行配置或数据库；没有创建 migration，没有读取/覆盖科研资料，没有调用真实 LLM，没有启动 Goal。
- 已按独立设计单元创建本地 Git 提交；本轮未请求推送，未推送这些新提交。

## 实施后验收与下一步

SQLite migrations、单元/集成测试、旧功能回归及 Cockpit 合成文本/JSON/vision 已完成；真实论文 Chat 已通过。Skeleton 长结构请求、浏览器视觉/键盘闭环、PostgreSQL 并发和更多论文语义评测仍需完成。没有独立测试 DeepSeek 真实服务；旧 DeepSeek 路径通过现有 mock 回归。CLI strict 检查和代理 smoke 均不替代新功能验收。

真实 Evidence ID 只能证明来源真实与可访问，不能自动保证语义蕴含；实施验收必须逐条人工核查重要 claim。默认同步 90 秒和批次数上限是初始设计预算，长文可能只得到明确 partial 结果，不能承诺任意长度论文的一次性完整分析。

后续 Goal 建议顺序：**A → B → C → D → E → F**。每项先实现并验证所属契约，再提交；最后执行全链路及 legacy 回归。D/E 可在概念上独立，但共享 models.py 和迁移链，建议实际串行。
