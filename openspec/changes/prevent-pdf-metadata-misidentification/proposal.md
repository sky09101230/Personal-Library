## Why

PDF 可能同时包含论文 DOI 与同名研究数据 DOI，也可能把 `untitled` 等生成占位符写入内嵌标题。当前选择与冲突校验会因此把数据集当论文、或把占位符当真实标题；同时补充材料关键词自动分类存在正文误判风险，需要先停用。

## What Changes

- DOI 候选标题同样匹配时，优先选择具有期刊或会议出版容器的文献记录，而不是同名数据集记录。
- 将已知 PDF 生成占位标题视为缺失值；能提取首页标题时使用首页标题，不能提取时也不得让占位标题触发冲突或写入规范 metadata。
- **BREAKING** 网页 PDF 上传暂时停止根据文件名、PDF 标题或页面关键词自动识别补充材料；所有新上传文件先按正文处理。
- 保留历史补充材料记录、文件角色、展示和正文优先下载语义，不改动现有附件数据。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `doi-bibtex-metadata`: 收紧多 DOI 选择和 PDF 占位标题处理规则。
- `literature-ingestion`: 停止网页上传入口的补充材料自动推断，同时保留历史文件角色语义。

## Impact

- 受影响代码：`apps/box_upload/metadata.py`、`apps/box_upload/views.py` 及对应测试。
- 受影响数据：两条已报告记录已经人工修正，本变更只验证现状，不重复写库；历史补充材料记录保持不变。
- 不增加数据库迁移、第三方依赖、外部服务或新的上传步骤。
