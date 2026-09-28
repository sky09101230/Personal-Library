# Paper Intelligence V1 实施前准备

状态：仅设计，禁止据此宣称已经实现。总体决策见 [0045](../decisions/0045-paper-intelligence-v1.md)。

## 依赖与范围

数据库执行策略遵循 [0046](../decisions/0046-paper-intelligence-sqlite-first.md)：V1 先用现有 SQLite，PostgreSQL 实例、迁移与并发实测不阻塞本轮实施和 SQLite 版本验收；它们是未来切换 PostgreSQL 前的必做项。

复用 Python 3.13、Django 5.2、urllib/json/hashlib/zipfile/tempfile、现有本地/NAS storage、PyPDF/MinerU 的 normalized/raw artifact、LiteratureChunk、DocumentAnalysis、登录/CSRF 与原生 PDF 流。V1 无新增 pip 服务依赖，不需要 OpenAI SDK、Redis、Celery、Qdrant、Milvus 或 SQLite FTS。若后续图片尺寸校验确需库，编码前单独论证依赖，不能隐式安装。

仅管理员配置 PAPER_LLM_* 与三个 model role；兼容旧 DEEPSEEK_*。本机候选 endpoint 为 http://localhost:53347/v1，不把它硬编码为生产默认，不在仓库保存任何真实 key。初次设计阶段不连接模型、读取本机论文、操作数据库、创建 migration 或修改 .env；后续按用户要求的前置验证仅使用用户自行填写的 .env 做合成 API smoke，不读取论文或创建功能 migration，详见文末复核结果。

## 实施前必须核实

- Git 分支/工作区无冲突，migration leaf 与部署数据库种类确认。
- 本机代理的模型名、认证是否必需、JSON mode、vision、输入输出窗口和总耗时；通过人工配置，不猜模型名。
- 反向代理/ASGI timeout 大于 90 秒业务 deadline；失败可重读 run 状态。
- 原 parse artifact 与 raw bundle 的合法测试数据用合成 JSON/ZIP/空白 PDF，不提交真实论文。
- 图像签名与尺寸检查使用有界读取；若不能安全支持某格式，就只支持已验证 PNG/JPEG，其余标 unavailable。
- 新模块默认功能开关关闭，逐个验收后启用；旧 Overview 保持运行。

## 初始资源预算（实现配置可下调，测试需固定）

| 边界 | 初始默认上限 |
| --- | --- |
| 单问题 / prompt 历史 | 4,000 字符 / 最近 6 轮，仍服从总预算 |
| rewrite | 最多 4 条、各 256 字符、1 次模型调用 |
| Evidence / claim 引用 | Chat 最多 24 项；每 claim 1–8 个 ID |
| provider response | 2 MiB；单 HTTP 30 秒且服从总 deadline |
| 单生成总 deadline | 90 秒；lease 120 秒 |
| Skeleton | 最多 4 个 extract batch + 1 个 reduce，超限明确 partial |
| 输入 token 安全余量 | 配置窗口减去输出预留，再保留 10%；未知窗口必须配置 |
| normalized JSON / raw bundle 下载 | 128 MiB / 512 MiB，有界流及临时文件 |
| ZIP 单 segment / 成员总数 / 压缩比 | 256 MiB / 每层 10,000 / 100:1 |
| image | 10 MiB、40 MP，最多 4 张/模型调用 |
| 无 tokenizer 文本估算 | 按完整序列化 UTF-8 字节数保守计算，记录 estimated=true |

图像 token 无可靠估计时必须配置 provider 图像预算或禁用 vision，不按零费用计算。预算不足不得跳过安全校验。以上为设计初值，不是性能测试结果。

## Change 清单与执行门槛

| 顺序 | Change | 前置 | 通过后可用能力 |
| --- | --- | --- | --- |
| A | unify-paper-llm-provider | 无 | 中立模型 transport + DeepSeek 兼容 |
| B | add-paper-evidence-layer | 无 | 单篇权限、parse 选择、四类证据和图片 resolver |
| C | add-paper-retrieval-context | A、B | 跨语言检索和有覆盖报告的 ContextPacket |
| D | add-evidence-grounded-paper-chat | A、B、C | 持久化、隔离、多轮、严格引用 Chat |
| E | add-paper-skeleton-overview | A、B、C；实施在 D 后 | 新分析类型、缓存、再生成、长文 Skeleton |
| F | integrate-paper-intelligence-reader | A–E | 阅读界面及完整证据导航 |

每项实施先看 proposal/design/spec/tasks，实施后运行对应测试、迁移检查与 strict validate；通过即独立 Git 提交。任务 checkbox 本轮保持未完成。不得因为 CLI spec 校验成功而勾选实现任务。

## 验收测试矩阵

| 维度 | 必须覆盖的合成用例 | 归属 |
| --- | --- | --- |
| Provider | /v1 拼接、DeepSeek 回退、loopback、恶意 host、userinfo、跳转、proxy、401/429/5xx/超时、截断/空/非法 JSON、无 usage、vision unsupported、日志不泄漏 | A |
| 来源 | v1/v2、585 页 segment、跨页 span、空 Figure、重复图号、Figure 1/10、缺 caption/asset、同页/跨页 source_index、table/equation、artifact 校验失败、ZIP traversal/bomb、未发布 | B |
| 引用 | 不存在、跨论文、跨 parse、同 parse 但未送入上下文、旧 schema、伪页码、越界 offsets、幻觉 Figure、文档 prompt injection | B + D/E 消费测试 |
| Retrieval | 中文“非相干光”命中 incoherent illumination、英文/缩略词、前轮指代、rewrite 失败、无匹配、未发布与补充材料隔离、稳定排序、去重 | C |
| 长文 | 120 页合成文档 Conclusion 在末页、末张 Figure 在后部、无 headings、超长 table、多图超过总预算、保底不足显式报错、coverage partial | C/E |
| Chat | 两用户同论文会话隔离、重复 request_id、并发 pending、lease 过期/迟到响应、重 parse、撤销发布、删除 parse、历史污染、model provenance | D |
| Skeleton | 论证链各项 claim、Figure 作用、证据不足、旧 v1/v2 不改、同 key 缓存、force 追加、provider/model 变化失效、失败保留旧成功、批次证据重新验证 | E |
| UI | 四区、Evidence 展开/键盘/跨页/图片/caption/无图回退、旧 parse 链接、XSS/HTML、登录/CSRF/越权、原 PDF Range、空/失败状态 | F |
| Migration | D/E 在 SQLite 升级前后 legacy 行不变、唯一/条件约束、删除关系；PostgreSQL 实测移至未来切换任务 | D/E |

自动测试全部用 mock provider，不调用外网。预备测试环境必须隔离本机 DEEPSEEK/MINERU 等真实配置，避免测试错误泄漏 key；可先装载 settings 再清理 provider 环境并使用占位值，不覆盖真实 .env。

语义质量人工验收：至少三类授权样本（方法图/实验图、长文、多语言或弱 OCR），每篇至少 5 个问题，含无法回答的问题；逐条核对重要 claim 与原文/页码，记录正确引用、语义支持、遗漏和拒答。自动 ID 校验率必须 100%；人工样本中的不受支持重要断言必须修复或明确拒答后才验收。真实样本、回答和评测记录留在忽略目录，仅提交去标识汇总。

## 后续 Goal 提示建议

“按 docs/decisions/0045、0046 与 preparation/17，使用现有 SQLite 依序实施六个 Paper Intelligence V1 Changes；先满足各自验收与 SQLite 迁移要求，每项通过后立即提交。禁止扩大到全库 RAG 或外网 research。沿用已定义 Evidence/ContextPacket 契约；最终验证端到端与旧 Overview/PDF 回归。PostgreSQL 实测属于未来切换任务，不阻塞本次 SQLite 版本完成，但不得宣称其已验证。”

本轮不创建或启动该 Goal。

## 2026-09-28 前置问题复核

历史场景继承与跨页 chunk 规范已修复，全仓 OpenSpec strict 33/33 通过。当前 Django check、makemigrations --check --dry-run、migrate --check 通过；完整回归 369 项中 362 通过、7 项因 NJU Box 已退役而按既有 skip 跳过。

本机代理经用户配置的 .env 认证后，模型列表及 gpt-6-luna 文本/JSON/合成图片 smoke 通过。这里只记录实际测试能力，不写入默认业务模型，不声称完整 context window 或真实论文质量已验证。新 provider 实现后仍需从其入口复验；当前模型 role 配置由实施阶段选择并验证。

本机 127.0.0.1:5432 探测不可达，PATH 未发现 psql/pg_ctl/postgres/docker；未声明不存在其它位置或远端 PostgreSQL，只能确认当前未提供可用测试环境。SQLite 路径已验证；PostgreSQL migration/concurrency 仍为部署到 PostgreSQL 前的硬验收项。新 Chat/Skeleton 的迁移、UI、安全失败路径和语义质量属于对应 Change 实施后的验收，不能在无实现时提前勾选。
