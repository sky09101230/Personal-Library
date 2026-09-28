## ADDED Requirements

### Requirement: 私有会话绑定不可变 parse
系统 MUST 将每个 conversation 绑定 user 和 DocumentParse，读取与写入 MUST 同时校验 owner 及当前文献发布权限。

#### Scenario: 他人请求会话
- **WHEN** 另一个已登录用户猜中 conversation UUID
- **THEN** 返回不可访问，不泄漏问题、回答或 evidence

#### Scenario: 未发布论文
- **WHEN** 文献取消发布后请求已有会话
- **THEN** 禁止访问派生答案和证据，不调用 provider

### Requirement: 结构化回答逐条引用
系统 MUST 只从经 B/C 提供的 Evidence 生成 supported claims，成功前执行 schema、allowlist 与来源验证。

#### Scenario: 正常科研问题
- **WHEN** 上下文足以说明方法或结果
- **THEN** 回答各重要结论带真实 Evidence ID，page/链接由后端派生

#### Scenario: 无或伪证据
- **WHEN** 响应 claim 无引用、引用未知/跨 parse/未入包 ID 或包含自造 page
- **THEN** 整个 turn 标 failed，不显示无证据答案

### Requirement: 不足证据明确拒答
系统 MUST 在检索不足时表达当前论文证据不足，不借外部知识、历史答案或 rewrite 充当依据。

#### Scenario: 论文没有相关证据
- **WHEN** 问题要求文中未能找到支持的结论
- **THEN** 返回 insufficient_evidence 或澄清问题，不补充外部推测

#### Scenario: 提示注入
- **WHEN** 正文或历史要求忽略系统提示并编造引用
- **THEN** 保持论文资料边界，不执行外部工具或放宽引用校验

### Requirement: 多轮上下文不升级为事实
系统 MUST 使用有界历史理解指代，复用历史 Evidence 时 MUST 重新装入并校验真实来源。

#### Scenario: 中文追问
- **WHEN** 上一轮提及 Figure 2，用户问这证明了什么
- **THEN** 在无歧义情况下重取其 caption/正文证据，引用仍属于本轮 allowlist

#### Scenario: 历史伪结论
- **WHEN** 历史回答含不受当前来源支持的表达
- **THEN** 不因历史出现就把它当作本轮事实

### Requirement: 持久化完整生成元数据
系统 MUST 保存 role/content、结构 payload、parse 关联、provider/model/prompt/schema、input fingerprint、context manifest、状态与 timestamps。

#### Scenario: 成功返回
- **WHEN** 完整响应通过验证
- **THEN** 同一原子提交写入 answer 与证据/provenance，GET 可按 sequence 重读

#### Scenario: provider 失败
- **WHEN** 网络超时、拒绝或非法 JSON
- **THEN** 记录安全 failed/error，不创建成功消息，不泄漏密钥

### Requirement: 并发与重试有明确语义
系统 MUST 通过 request_id、DB 唯一约束与有限 lease 控制重复和并发 turn，LLM I/O MUST 位于写事务外。V1 MUST 在 SQLite 上满足这些约束，不依赖 PostgreSQL 行锁或专属 SQL；PostgreSQL 验证属于后续数据库切换验收。

#### Scenario: 重复提交
- **WHEN** 相同 conversation/request_id 再提交
- **THEN** 复用同一 turn，不重复调用模型

#### Scenario: 同时不同问题
- **WHEN** conversation 已有 pending assistant
- **THEN** 新 request 返回 busy，只有一个 pending

#### Scenario: 过期和迟到返回
- **WHEN** lease 过期后被置 failed，原 provider 稍后返回
- **THEN** 不得覆盖 failed；用户可显式以新 request_id 重试

### Requirement: 重新解析不重绑定旧对话
系统 MUST 保留旧 conversation 的 parse，active parse 改变后旧对话只读，不允许旧引用静默指向新 parse。

#### Scenario: 新 parse 成为 active
- **WHEN** 用户打开旧 conversation
- **THEN** 显示版本过期及旧来源，继续提问要求创建新 conversation

#### Scenario: 生成中 active parse 切换
- **WHEN** 模型完成前 active parse 已不同
- **THEN** 本 turn 以 stale_parse 结束，不发布为新 parse 的回答

#### Scenario: 删除旧 parse
- **WHEN** 所属 parse 被正式删除
- **THEN** 按删除关系移除会话与消息，旧 URL unavailable
