## ADDED Requirements

### Requirement: 新增类型保留旧分析
系统 MUST 以 paper_skeleton 和独立 schema/prompt 保存新分析，并保持旧 Overview 类型、旧 payload、原 PDF 及 bibliographic metadata 不变。

#### Scenario: 升级含旧数据的数据库
- **WHEN** 存在 overview v1/v2 与 parse v1/v2
- **THEN** 迁移后旧数据仍可读且不自动转换或重新 parse

#### Scenario: Skeleton 生成失败
- **WHEN** 新模型调用或引用校验失败
- **THEN** 旧成功 Overview/Skeleton 仍可读，原 processing job 状态不变

### Requirement: 科研论证结构逐项有证据
系统 MUST 为 introduction、motivation、gap、proposed idea、method、experiments、results、conclusion 提供有引用的 claims 或明确缺证状态。

#### Scenario: 论文论证充分
- **WHEN** 输入覆盖方法、实验与结论
- **THEN** 各项解释带 Evidence，明确区分作者结果与分析性解读

#### Scenario: 原文缺少某环节
- **WHEN** 论文没有实验或没有明确 Gap
- **THEN** 对应项标 insufficient_evidence，不按模板补造

### Requirement: Figure 解读包含论证作用
系统 MUST 对纳入分析的 Figure 说明验证问题、设置、观察和论证作用，每个重要字段有 Evidence，并记录未处理图。

#### Scenario: 主要实验图
- **WHEN** Figure caption 和正文给出实验设置与结果
- **THEN** 分别提供问题/设置/结果/作用的受证据约束解读，链接到真实 Figure/caption/mention

#### Scenario: 图像不可读
- **WHEN** asset 不可用或未配置 vision
- **THEN** 显示 text_grounded，仅使用 caption/正文，不声称看见像素细节

#### Scenario: 超出可处理图数
- **WHEN** 完整 inventory 超出总调用预算
- **THEN** 记录 omitted figure 及原因，结果标 partial，不静默忽略尾图

### Requirement: 分批总结不能脱离原始证据
系统 MUST 在 extract 与 reduce 两阶段验证 Evidence，reducer MUST 接收最终候选 claims 对应的原始 excerpt。

#### Scenario: 长文需要多个批次
- **WHEN** C 提供覆盖全文的 section/figure 批次
- **THEN** 按有界计划执行，并将 conclusion 和尾部 Figure 纳入覆盖核算

#### Scenario: 中间摘要幻觉引用
- **WHEN** extract 产生未入包 ID 或 reducer 只有生成文本却缺原始来源
- **THEN** 拒绝相应成功结果，不把摘要当作 Evidence

#### Scenario: 调用预算耗尽
- **WHEN** 达到调用数或总 deadline 上限
- **THEN** 明确失败或 partial，不能标完整分析

### Requirement: 缓存指纹包含生成配置
系统 MUST 将来源、实际 context、各层版本、provider/model/参数、language 与 vision 模式纳入 fingerprint/cache key，密钥不得入库。

#### Scenario: 相同配置普通生成
- **WHEN** 同 parse 相同 logical generation_key 已有成功结果
- **THEN** 复用该结果，不重复调用模型

#### Scenario: 模型或上下文变化
- **WHEN** 模型、provider profile、prompt 或预算改变实际 context
- **THEN** 不命中旧生成缓存，生成新记录并保留旧 provenance

#### Scenario: 分批与视觉使用不同模型
- **WHEN** 一次生成包含不同 role 的 extract、reduce 或 vision 调用
- **THEN** context manifest 分别保存各次 provider、requested/returned model、prompt、输入哈希和实际 allowlist，所有调用计入统一总额度

### Requirement: 显式再生成追加结果
系统 MUST 用 PaperAnalysisRun 管理幂等 request、有限 lease、force nonce 和失败，禁止覆盖原成功 analysis。

#### Scenario: 强制生成成功
- **WHEN** 用户显式 POST force
- **THEN** 以新 nonce/fingerprint 追加 DocumentAnalysis，旧行不变

#### Scenario: 重复与并发
- **WHEN** 重复 request_id 或同 parse/type 已有 pending run
- **THEN** 复用原 run 或返回 busy，不创建多个活动生成

#### Scenario: 重试迟到
- **WHEN** lease 过期后的 provider 返回
- **THEN** 不能覆盖失败 run 或替换旧成功显示

### Requirement: 发布与版本在保存前重检
系统 MUST 在模型输入与结果保存前验证当前 published/active parse，并将运行上下文与引用清单持久化。

#### Scenario: 生成期间切换 parse
- **WHEN** 新 parse 成为 active
- **THEN** 返回 stale_parse，不把旧来源分析伪装为新 parse 结果

#### Scenario: 撤销发布
- **WHEN** 管理员在生成中取消发布
- **THEN** 不保存可见成功分析，返回安全不可用状态
