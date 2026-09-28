## ADDED Requirements

### Requirement: 检索范围限定单篇正式 parse
系统 MUST 只对 B 授权的同一 parse Evidence 进行检索，不读取其它论文、未发布或 supplementary 来源。

#### Scenario: 混合目录输入
- **WHEN** 调用方传入不属于当前 parse 的候选
- **THEN** 拒绝输入，不以全库相似性补齐

#### Scenario: 正常英文查询
- **WHEN** 问题匹配同篇若干段落
- **THEN** 返回有序 Evidence 候选及 lexical/结构分项得分，顺序可重复

### Requirement: 多语言改写只是检索辅助
系统 MUST 保留原问题并以有界 rewrite 提升跨语言召回，改写结果 MUST NOT 成为事实 Evidence。

#### Scenario: 中文提问英文正文
- **WHEN** 用户问为什么使用非相干光，mock rewrite 返回 incoherent illumination
- **THEN** 目标英文段落进入合成 fixture Top-5，最终引用只指向原文 Evidence

#### Scenario: 改写失败
- **WHEN** provider 超时或输出非法查询
- **THEN** 使用原词和可用原文术语检索并标降级；没有匹配则 insufficient_retrieval

#### Scenario: 指代歧义
- **WHEN** 历史同时提及两张图而用户只问它说明什么
- **THEN** 返回澄清需要或保留歧义，不擅自指定一张图

### Requirement: 结构与邻接扩展保持定位
系统 MUST 利用 heading/section/page/caption/figure mention 排名和有界邻接扩展，且去除重复或重叠来源。

#### Scenario: 明确 Figure 问题
- **WHEN** 问题指定 Fig. 2
- **THEN** 优先其 caption、相关正文及 Figure ID，不误匹配 Fig. 20

#### Scenario: 扩展命中段落
- **WHEN** 正文命中且相邻段落存在
- **THEN** 最多扩展前后各一段，保持 section 边界和真实 span

### Requirement: 实际上下文决定引用许可
系统 MUST 根据最终发送的片段建立 allowlist；截取片段 MUST 有对应精确 locator，历史回答与 rewrite 不在 allowlist。

#### Scenario: 长 chunk 仅发送一部分
- **WHEN** 预算导致文本按源 span 截取
- **THEN** 生成该 span 的 locator，并只许可实际发送 Evidence

#### Scenario: 复用历史引用
- **WHEN** 用户追问前轮结论
- **THEN** 重新加载并校验旧 Evidence，将原文送入本轮才允许再次引用

### Requirement: 上下文预算覆盖整个请求
系统 MUST 计算 prompt、JSON、history、source、图片和输出预留，并在无法满足保底时显式失败。

#### Scenario: 未知 tokenizer
- **WHEN** profile 没有 tokenizer
- **THEN** 使用 UTF-8 字节保守估算并记录 estimated，不宣称准确 token 数

#### Scenario: 极小窗口
- **WHEN** 剩余预算不足最小必需证据
- **THEN** 返回 context_budget_exceeded，provider 不收到超限 packet

### Requirement: Skeleton 覆盖全篇结构
系统 MUST 先建立完整 section/figure inventory，再给 Abstract、Introduction、Method、Results、Conclusion 和 Figures 分配预算，不按文首顺序截断。

#### Scenario: 长篇尾部证据
- **WHEN** 合成 120 页文章的 Conclusion 和末张图位于尾部
- **THEN** 批次计划包含 Conclusion span 和尾图 caption/mention，coverage 记录总 inventory

#### Scenario: 缺标题或过多图
- **WHEN** 论文没有显式 heading 或图数超出最大批次可容纳量
- **THEN** 标 inferred_section 或 partial/omitted 原因，不声称已完整覆盖

### Requirement: Packet 版本和指纹可复现
系统 MUST 保存 parse/hash、Evidence/retrieval/context/rewrite 版本、实际 items、预算、query 和 coverage 并确定性计算 packet fingerprint。

#### Scenario: 同输入再次构建
- **WHEN** 相同来源、查询改写结果、版本与预算
- **THEN** 生成相同 packet fingerprint

#### Scenario: 预算或版本变化
- **WHEN** 任一上下文版本、实际片段或预算变化
- **THEN** fingerprint 变化，消费者不能复用旧输入缓存
