# Django 与文献对象存储准备

## 运行环境

- Python 3.14
- Django 5.2.17
- NAS WebDAV 与历史 NJU Box 适配器均使用 Python 标准库发送 HTTPS 请求，不需要额外 HTTP 客户端依赖。

## 本机配置

复制 `.env.example` 为 `.env`。本地开发可选择 SQLite；当前部署使用 PostgreSQL：

```dotenv
DJANGO_SECRET_KEY=replace-for-local-use
DJANGO_DEBUG=true
AGENTSYS_DB_ENGINE=sqlite

LITERATURE_STORAGE_BACKEND=nas_webdav
NAS_WEBDAV_BASE_URL=https://nas.example.edu:5006
NAS_WEBDAV_USERNAME=
NAS_WEBDAV_PASSWORD=
NAS_WEBDAV_LITERATURE_ROOT=/public/PLAB_KnowledgeBase/Literature
```

新文件默认写入 NAS WebDAV。每条上传记录保存自己的 `storage_backend`，读取和删除时按记录选择 NAS 或历史 NJU Box，不能根据当前默认值猜测旧文件的位置。只有仍需读取历史 NJU Box 记录时，才保留对应的 NJU Box 配置。

`.env` 只保存在服务器本机，不进入 Git 或同步目录；真实密钥和密码不得写入文档、日志或命令历史。
