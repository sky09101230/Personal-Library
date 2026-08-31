## Why

网页上传会在上传者看到解析结果前直接创建正式文献记录，错误标题、错误 DOI 或缺失期刊只能交给不熟悉论文内容的管理员事后修正。上传者应在本次上传页面完成 metadata 核对，正式文献表只接收已经确认的结果。

## What Changes

- PDF 文件先写入 NAS 暂存并提取 metadata，但不创建正式 `CanonicalDocument` 或 `UploadedDocument`。
- 浏览器继续以最多四个并行通道传输批次文件，并分别显示通道进度。
- 上传页面在文件选择区下方展示本批解析结果；缺标题项标红，缺期刊项标黄。
- 上传者可手动修改标题，也可修改 DOI 后重新解析该项 metadata。
- 只有本批每项标题均已补全、期刊缺失警告已由上传者核对后，系统才在事务中写入正式文献记录并发布。
- 上传者可取消未确认批次，系统删除对应 NAS 暂存文件；暂存内容不进入 Library、MCP 或管理员 metadata 审核队列。

## Capabilities

### New Capabilities

- `upload-metadata-confirmation`: 约束上传批次暂存、解析结果展示、上传者修正与确认后入库行为。

### Modified Capabilities

- `automatic-literature-publication`: 网页上传文献改为在上传者确认 metadata 后发布，而不是文件传输完成后立即发布。
- `literature-object-storage`: 网页上传允许先持久化 NAS 暂存对象，再于 metadata 确认后创建正式上传记录。

## Impact

影响文献上传模型与迁移、上传视图和路由、NAS 删除调用、上传页面 JavaScript/CSS 及上传回归测试；不新增第三方依赖，不改变 MCP 与 Zotero 导入流程。
