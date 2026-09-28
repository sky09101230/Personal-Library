## ADDED Requirements

### Requirement: 来源目录稳定且 parse 隔离
系统 MUST 从真实 parse 和 chunk locator 生成带版本的 Text、Figure、Table、Equation Evidence ID；相同 parse 同版本 MUST 稳定，新 parse MUST 使用不同身份。

#### Scenario: 重建同一目录
- **WHEN** 相同 parse/hash/builder/chunk manifest 重建 EvidenceCatalog
- **THEN** 相同 locator 得到相同 ID，原始 artifact 不变

#### Scenario: 重新解析
- **WHEN** 同一 PDF 新建另一 DocumentParse
- **THEN** 新旧 Evidence 不混用，旧 ID 只能解析到旧 parse

### Requirement: 正式资料门禁与 parse 选择
系统 MUST 在目录读取、模型 context 与证据读取前检查登录、canonical published、upload uploaded/primary 及 parse 完整性。

#### Scenario: 待审核资料
- **WHEN** 请求未发布 canonical、UploadReviewItem 或 supplementary parse
- **THEN** 拒绝进入正式 Evidence/模型上下文，provider 不被调用

#### Scenario: Overview 失败
- **WHEN** 没有旧成功 parse，但存在只在 overview 阶段失败的完整 parse
- **THEN** 允许其作为可读来源，显示旧 job 失败不代表 parse 无效

#### Scenario: 旧成功仍可用
- **WHEN** 新 job 运行中或失败且已有成功 parse
- **THEN** 默认保留旧成功 parse，不能混用新失败 job 的 Evidence

### Requirement: 跨页来源按真实 span 定位
系统 MUST 从 source_spans 和块内容推导页码、offset、section 与 bbox；无来源字段不得补造。

#### Scenario: 跨页文本块
- **WHEN** 一个 chunk 引用位于两个页的 blocks
- **THEN** 各 Evidence locator 对应实际页/span，不能一律使用 chunk 起始页

#### Scenario: PyPDF 旧数据
- **WHEN** parse v1 没有 blocks 或 bbox
- **THEN** 仅生成 text evidence 和真实页定位，并明确无结构能力

### Requirement: Figure 为一级来源
系统 MUST 编目无文本 figure，关联可验证 caption、section 和正文 mention，并保留歧义与缺失状态。

#### Scenario: 有 caption 与正文引用
- **WHEN** Figure 1 有同源 caption 且后文明确提及 Fig. 1
- **THEN** 目录提供 Figure、caption Evidence 和该段 mention 的实际 locator

#### Scenario: 图号或源位置歧义
- **WHEN** Figure 1/10、重复图号或跨页重复 source_index 同时存在
- **THEN** 不误绑，歧义项保留待核查状态，不凭空生成 panel 图片

### Requirement: 图片通过有界 resolver 读取
系统 MUST 通过 parse 的 raw bundle 和验证后的 handle 读取单个安全栅格 asset，禁止任意路径/URL 和整包解压。

#### Scenario: 嵌套合法图片
- **WHEN** asset 位于某 segment 的 content_list 相对图片目录
- **THEN** 返回该图片字节与正确 MIME，不返回存储凭据或 remote_path

#### Scenario: 恶意或超限压缩包
- **WHEN** 出现 traversal/盘符/符号链接/重复路径/压缩炸弹/超大图片
- **THEN** 拒绝 asset 读取并保留可用 caption 与 PDF 导航，不降级为不安全 URL

#### Scenario: 旧包缺图片
- **WHEN** raw artifact 缺失或不能唯一确定图片成员
- **THEN** 标 asset_unavailable，不把外部 URL 当替代图片

### Requirement: 引用必须来自实际输入集合
系统 MUST 在成功写入前验证每条 claim 的 Evidence ID 属于实际 ContextPacket allowlist、当前 parse 及真实来源，禁止模型产生 citation locator 字段。

#### Scenario: 同 parse 未给模型的 ID
- **WHEN** 返回 ID 存在但未被装入本轮实际输入
- **THEN** 拒绝该输出，不持久化成功答案

#### Scenario: 伪造定位或跨 parse
- **WHEN** 返回伪 ID、page 字段、其它 parse ID 或越界 span
- **THEN** 拒绝整个成功 payload，不静默删引用

#### Scenario: 调用中撤销发布
- **WHEN** 模型返回前文献已不再 published
- **THEN** 重检失败，不向用户发布生成结果

### Requirement: 表格公式保留原始来源
系统 MUST 提供可溯源 table/equation 及其真实文本结构，生成解释不能成为新的原文 Evidence。

#### Scenario: 无 cell bbox
- **WHEN** 表格仅有 HTML body 与整表 bbox
- **THEN** 提供安全文本及整表位置，不生成单元格坐标

#### Scenario: 解释公式
- **WHEN** LLM 返回公式理解
- **THEN** 只允许引用真实 equation/text ID，解释保存在派生结果中
