# 文献 metadata 服务准备

## 运行依赖

- Python 3.12
- Django 5.1.7
- `pypdf==6.1.3`：读取 PDF 嵌入 metadata 和前两页文本
- Crossref REST API：仅在 PDF 中提取到 DOI 后查询精确 work
- Zotero Web API v3：按个人或群组 library 单向导入 top-level items

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

`CROSSREF_MAILTO` 用于形成可识别的 API User-Agent。Zotero API Key 不写入 `.env`，由用户在导入页输入并仅用于该次请求。

## 发布与复核

新上传或新导入的文献默认不发布。管理员在 Django 后台检查 title、authors、DOI、证据与冲突候选后，手工将 `index_status` 改为 `published`。只有此状态的文献可被 MCP Agent 工具读取。

## 当前边界

- pypdf 不能可靠处理扫描 PDF；扫描件会保持待处理状态。
- 无 DOI 文献不会执行标题模糊匹配，避免错误自动绑定。
- Zotero 首版不下载 PDF 附件、不保存 Collection 层级、不做增量或双向同步。
- Crossref 或 Zotero 网络失败需要用户稍后重试；PDF 上传本身不因 Crossref 失败而失败。
