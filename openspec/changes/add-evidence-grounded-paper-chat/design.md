# Evidence-grounded Paper Chat

## Context

Conversation 必须属于 user 与固定 DocumentParse，不能只记录 canonical ID 后每次自动使用最新 parse。复用 B 的授权、C 的上下文和 A 的 transport，模型正文不直接拼接到 HTML。

## Decisions

1. 模型字段完全遵循 0045 第 7 节。conversation UUID 随机，不以 ID 不可猜代替 owner 校验。user+parse 可有多 conversation；canonical/upload 从 parse 推导。
2. 消息 role 仅 user/assistant；system prompt 由版本代码管理，不接受客户端 system role。assistant 保存结构 payload、服务端组合 answer、context_manifest、allowlist、provider/model/schema/prompt/fingerprint 及状态时间戳。manifest 分别记录 rewrite 与 answer（以及可选 vision）调用的 purpose、provider、requested/returned model、prompt version、输入哈希、实际 allowlist 与可空 usage，顶层 model 代表最终回答模型。
3. POST create conversation：document_id+显式 parse_id 需匹配 B active parse；POST turn：question+request_id，客户端不得设置 provider、user、role、evidence 或 locator。GET messages 按 sequence 分页且 owner-only。匿名不调用 provider；错误返回安全码。
4. 短事务创建 user 与 pending assistant，唯一 conversation+turn+role 和 conversation+sequence；条件唯一约束保证每会话一个 pending assistant。事务外执行 retrieval/provider，完成时再次核验 owner/published/active parse 和 lease，再原子更新。
5. 重复 request_id 返回已有 turn；不同 request 遇 pending 返回 409 busy。pending lease 120 秒、生成 deadline 90 秒；过期由下一次状态读取/提交惰性转 failed。迟到 provider 不能覆盖终态，retry 显式创建新 request_id，失败 turn 仍可审计。
6. prompt 最多近六轮且服从预算；只用成功轮次作指代语境，历史 answer 不作为来源。旧 Evidence 若复用，C 重取并加入本轮 allowlist。论文文字与聊天内容中的越权提示都当数据，不能启用外网或改变 system 指令。
7. 输出 personal.paper-chat.v1：status supported/insufficient_evidence、claims[]、clarification_question（可空）。supported 每个事实/判断/结论都有非空 evidence_ids；answer 从通过 validator 的 claims 生成。没有自由文本 summary 后门。insufficient 状态只允许固定说明及澄清问题，不补背景知识。
8. schema/ID 校验失败、provider 错误均 failed，不把半成品 answer 发给浏览器。V1 不流式输出未验证 token；前端可 GET 查询成功/失败状态。日志只记录安全错误码与运行 ID。
9. active parse 改变后旧 conversation 只读，保留原 parse 链接；正在生成的 turn 终态 stale_parse，不移接新 parse。取消发布撤销旧 Chat/证据访问；硬删 user/parse 清理 DB 对话。业务不复制原始 PDF 或生成 evidence 文件。

## Acceptance and Tests

两个用户共享同一正式论文但无法读取彼此会话；重复/并发/超时/迟到输出必须确定；伪 ID、同 parse 未入包 ID、无证据断言和恶意文档不生成成功答案；中文 follow-up 仍定位真实英文来源。单元测试覆盖服务层与权限，F 再测实际阅读器。

## Risks and Compatibility

有界同步请求适合单机低并发，超时可重读终态，未来有吞吐证据再加 DB worker。SQLite 条件唯一约束和原子条件更新是并发边界，不能依赖 select_for_update 在 SQLite 的行锁能力。原 parse job/旧 overview 不受聊天失败影响。

## Goals / Non-Goals

目标：提供仅依据当前论文真实 Evidence 的多轮私有会话，成功回答必须通过公共引用校验并完整持久化 provenance。

非目标：不做跨论文 memory、SSE token 流、外网工具、MCP Chat、分享会话或后台复杂任务编排。

## Dependencies and Ownership

依赖 A unify-paper-llm-provider、B add-paper-evidence-layer、C add-paper-retrieval-context；UI 由 F；迁移先于 E 顺序生成。

受影响模块：models.py 新增 PaperConversation/PaperChatMessage；新增 paper_chat.py、chat_views.py、chat_urls.py、test_paper_chat.py、test_chat_views.py 和增量 migrations；最终项目路由组合由 F。

## Migration Plan

新增两表和外键/唯一约束；旧表无回填。V1 在 SQLite 上验收迁移与并发，保留现有 parse/analysis；模型保持 Django ORM 可移植性，PostgreSQL 实测按决策 0046 留到未来切换前，不阻塞 V1。user/parse/conversation 删除 CASCADE 消息，遵循已有 upload 删除关系。回滚先禁用入口并保留表。

## Acceptance Criteria

必须通过本 Change 全部 spec 场景、对应测试和 strict validation。真实 provider、PostgreSQL 和语义评测未验证项单独报告；本轮不实施。公共契约遵循 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)。
