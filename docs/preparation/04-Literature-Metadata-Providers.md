# 文献 metadata 服务准备

## 运行依赖

- Python 3.14
- Django 5.2.17
- `pypdf==6.1.3`：读取 PDF 嵌入 metadata 和前两页文本
- Crossref REST API：仅在 PDF 中提取到 DOI 后查询精确 work
- Zotero Web API v3：连接个人或群组 library，浏览 Collection 并选择 top-level items 导入

安装依赖并执行迁移：

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

## 配置

在 `.env` 中配置：

```dotenv
CROSSREF_API_URL=https://api.crossref.org
CROSSREF_MAILTO=researcher@example.edu
ZOTERO_API_URL=https://api.zotero.org
METADATA_HTTP_TIMEOUT=5
```

`CROSSREF_MAILTO` 用于形成可识别的 API User-Agent。Zotero API Key 不写入 `.env`；管理员首次连接时输入，系统加密保存且不在页面回显。

## 发布与复核

PDF 成功写入对象存储后，规范文献记录立即发布；只有 Zotero metadata、尚无 PDF 的记录继续保持待处理。管理员仍可复核 title、authors、DOI、证据与冲突候选。MCP Agent 只读取 `index_status=published` 的文献。

## 当前边界

- pypdf 不能可靠提取扫描 PDF 的文字；这类文件的 metadata 会保持待补全或待复核，但不改变已成功保存 PDF 的发布状态。
- 无 DOI 文献不会执行标题模糊匹配，避免错误自动绑定。
- Zotero 只导入明确选择的浏览器 PDF，或 Zotero 中 `imported_file + application/pdf` 的托管附件；跳过网页快照、URL 附件和 linked file，不做双向同步。
- 浏览器 PDF 优先；未选择时，服务器上的 Zotero Desktop 可读文件优先于 Zotero Web 下载。单个 PDF 失败时保留 metadata 并继续处理其他条目。
- 网页上传从 PDF 提取到 DOI 时，DOI/BibTeX 预检失败会在写入对象存储前停止整批；后续 metadata 补全失败不会删除已成功保存的 PDF。
