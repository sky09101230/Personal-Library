## Purpose

为已保存的原始文献 PDF 提供与上传及书目元数据隔离、可版本化重建、并能从 AI 结论稳定追溯到文本块和原始页码的派生处理基础层。

## ADDED Requirements

### Requirement: 原始文献与派生内容保持隔离
系统 MUST 将 PDF、规范文献和书目元数据视为原始记录，将解析产物、文本块和 AI 分析视为可重新生成的派生记录。文献处理不得修改原始 PDF 或规范文献的 bibliographic metadata。

#### Scenario: 文献处理成功
- **WHEN** 一个已上传的主 PDF 完成处理
- **THEN** 系统创建新的解析、文本块和分析记录
- **AND** 原始 PDF、标题、摘要、作者、DOI 及其他书目元数据保持不变

#### Scenario: 文献处理失败
- **WHEN** parser、chunker、AI provider 或派生 artifact 存储失败
- **THEN** 系统记录失败阶段和受控错误
- **AND** 已成功的 PDF 上传及其原始记录保持可用

### Requirement: Parser 输出使用中立且保留页码的契约
系统 MUST 将 parser 后端输出转换为 PLAB 自有的版本化中立 schema，下游处理不得依赖任一 parser 的原始响应格式。中立 schema MUST 按原 PDF 页码保留每页文本。

#### Scenario: PyPDF fallback 解析多页 PDF
- **WHEN** 系统使用默认 fallback parser 解析一个多页 PDF
- **THEN** parser 按原顺序返回从 1 开始的页码和每页文本
- **AND** 下游只消费中立 schema

#### Scenario: 某页没有可提取文本
- **WHEN** parser 无法从某一页提取文本但 PDF 仍可解析
- **THEN** 中立结果仍保留该页页码和空文本
- **AND** 后续页面的页码不发生偏移

### Requirement: 文本块稳定追溯到原始页
系统 MUST 将中立解析结果分为稳定、有序的文本块。PyPDF v1 的页文本 chunker MUST 保持页内分块；structured parse v2 的结构 chunker MAY 跨页组合相同 section 的连续文本，但 MUST 保存起止页及逐段 source_spans。每个文本块 MUST 能经由解析记录和上传记录追溯到规范文献、原始 PDF 与明确页码。

#### Scenario: 创建文本块
- **WHEN** 一个包含可提取文本的解析结果完成分块
- **THEN** 每个文本块记录所属 parse、顺序、稳定标识、文本内容和原始页码
- **AND** 页文本 chunker 生成的块不跨页，结构 chunker 的跨页块记录真实起止页和每段 block/page/offset 来源

#### Scenario: 结构化文本跨页
- **WHEN** structured parse v2 的同 section 文本跨越两页且满足结构 chunker 的合并预算
- **THEN** 文本块可跨页，并通过 source_spans 逐段保留 block_id、原始页号、chunk offsets 和 block offsets
- **AND** 任何具体片段的精确页定位以其 source span 为准，不把起始页当作所有片段的页码

#### Scenario: 对相同输入使用相同版本分块
- **WHEN** 相同的页文本使用相同 chunker 版本和参数重新分块
- **THEN** 系统生成相同顺序、边界和内容哈希的文本块

### Requirement: 处理链版本化且支持非破坏性重处理
系统 MUST 记录 pipeline、parser、chunker 和 prompt 版本，并通过追加新处理结果支持重新处理。系统不得先删除当前可用派生结果再生成替代结果。

#### Scenario: 重复 enqueue 当前版本
- **WHEN** 同一上传记录对当前版本重复请求处理且没有强制重处理
- **THEN** 系统复用已有活动任务或成功结果
- **AND** 不创建重复的 parse、chunks 或 analysis

#### Scenario: 强制重新处理
- **WHEN** 操作者对已有成功结果请求强制重新处理
- **THEN** 系统创建新的处理任务并保留旧任务及其派生结果
- **AND** 只有新任务成功后它才成为最新可用结果

### Requirement: 数据库队列支持异步处理和历史回填
系统 MUST 使用数据库记录队列和 management command worker 执行文献处理，并 MUST 提供有界的历史主 PDF backfill。该能力不得要求 Celery、Redis、Kafka 或新的队列基础设施。

#### Scenario: 新主 PDF 上传成功
- **WHEN** 一个新的主 PDF 上传记录已成功提交
- **THEN** 系统在独立事务完成后安全地 enqueue 文献处理任务
- **AND** enqueue 或后续处理失败不改变上传成功结果

#### Scenario: 回填历史文献
- **WHEN** 操作者运行 backfill command 并指定数量上限
- **THEN** 系统只为限定数量的可用主 PDF 创建或复用当前版本任务
- **AND** 重复运行不会为相同当前版本制造重复结果

#### Scenario: Worker 处理失败
- **WHEN** worker claim 的任务抛出解析、存储或分析错误
- **THEN** 任务进入 failed 状态并记录失败阶段、错误代码和安全错误信息
- **AND** worker 可继续处理后续排队任务

### Requirement: AI Overview 保持领域无关且证据有效
系统 MUST 将 AI Overview 与原文 abstract 分开保存。Overview MUST 只包含领域无关的短摘要、摘要、主题和关键点；每个正式保存的关键点 MUST 至少引用一个属于同一 parse 的合法文本块，并且声明页码与该文本块页码一致。

#### Scenario: 保存合法 Overview
- **WHEN** AI 返回结构合法且全部关键点证据属于当前 parse
- **THEN** 系统保存独立的 overview analysis 及其 provider、model、prompt version 和输入指纹
- **AND** 规范文献 abstract 不发生变化

#### Scenario: 拒绝不存在的文本块证据
- **WHEN** AI Overview 引用不存在或属于其他 parse 的 chunk
- **THEN** 系统拒绝保存该分析并将任务标记为受控失败

#### Scenario: 拒绝不一致页码
- **WHEN** AI Overview 的 evidence 页码与所引用 chunk 页码不一致
- **THEN** 系统拒绝保存该分析

### Requirement: 现有文献详情体验展示派生结果
系统 SHALL 在现有文献详情体验中展示最新处理状态、最新成功的 AI Overview、按页组织的 Parsed Text 以及关键点证据页码，同时保留现有原始 PDF 查看能力。

#### Scenario: 处理已完成
- **WHEN** 已登录用户查看具有成功处理结果的文献详情
- **THEN** 页面显示 Overview、topics、key points、证据页码和按页文本
- **AND** evidence 可以定位到对应原始 PDF 页

#### Scenario: 尚未处理或处理失败
- **WHEN** 文献没有成功结果或最新任务失败
- **THEN** 页面显示明确的 processing 状态和安全错误摘要
- **AND** 原始 PDF 的查看与下载仍然可用

### Requirement: 完整解析 artifact 与数据库索引分离
系统 MUST 将完整中立 parser artifact 保存到配置的文献对象存储，将 artifact 后端、路径、校验和、格式和 schema 版本保存到数据库。数据库中的页级 chunks 与分析索引用于常规读取，不得要求把 parser 原始大型响应整体写入数据库。

#### Scenario: 持久化解析结果
- **WHEN** parser 成功生成中立解析结果
- **THEN** 系统将完整 artifact 写入与源 PDF 兼容的已配置对象存储
- **AND** parse 记录保存可验证的 artifact 索引信息

#### Scenario: Parser 后端返回额外字段
- **WHEN** adapter 收到特定 parser 的额外原始字段
- **THEN** 下游 chunks 和 analysis 不保存或依赖这些后端专有字段
