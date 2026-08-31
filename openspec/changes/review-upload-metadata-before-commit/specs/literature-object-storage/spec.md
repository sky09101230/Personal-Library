## MODIFIED Requirements

### Requirement: 文件上传和元数据处理解耦
系统 MUST 允许网页上传先持久化远端暂存文件和暂存解析结果，并仅在上传者确认 metadata 后创建正式上传记录；metadata 解析、修正或正式入库失败不得丢失仍需重试的暂存对象追踪信息。

#### Scenario: 元数据解析完成但尚未确认
- **WHEN** PDF 已写入选定后端且暂存解析结果已保存，但上传者尚未确认
- **THEN** 系统保留远端对象和暂存记录
- **AND** 不创建正式上传记录

#### Scenario: 元数据重新解析失败
- **WHEN** 用户提交的 DOI 无法获得可用 metadata
- **THEN** 系统保留远端对象和原暂存结果，并允许用户修正后重试

#### Scenario: 非网页入口上传
- **WHEN** PDF 通过 MCP 或 Zotero 等非网页上传入口成功保存
- **THEN** 系统继续使用该入口既有的存储与 metadata 处理顺序
