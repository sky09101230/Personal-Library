## MODIFIED Requirements

### Requirement: 文件上传和元数据处理解耦
系统 MUST 允许 Browser 和 MCP 上传先持久化远端暂存文件和暂存解析结果，并仅在上传者确认 metadata 后创建正式上传记录；metadata 解析、修正或正式入库失败不得丢失仍需重试的暂存对象追踪信息。

#### Scenario: 元数据解析完成但尚未确认
- **WHEN** PDF 已写入选定后端且暂存解析结果已保存，但上传者尚未确认
- **THEN** 系统保留远端对象和暂存记录
- **AND** 不创建正式上传记录

#### Scenario: 元数据重新解析失败
- **WHEN** 用户提交的 DOI 无法获得可用 metadata
- **THEN** 系统保留远端对象和原暂存结果，并允许用户修正后重试

#### Scenario: 元数据处理失败
- **WHEN** Browser/MCP 的 PDF 已有可追踪暂存对象，但确认前元数据处理失败
- **THEN** 系统保留可追踪的暂存对象和仍可用的原暂存结果，不创建正式文献，并允许修正、重试或取消
- **AND** 对 Zotero 等保留既有顺序的入口，正式上传已成功后的元数据失败仍不得回滚远端对象和正式上传记录

#### Scenario: Zotero 入口上传
- **WHEN** PDF 通过 Zotero 导入入口成功保存
- **THEN** 系统继续使用该入口既有的存储与 metadata 处理顺序

#### Scenario: MCP 入口上传
- **WHEN** PDF 通过 MCP 上传入口成功保存和解析
- **THEN** 系统保留远端对象和上传者私有的暂存记录
- **AND** 在上传者网页确认前不创建正式上传记录
