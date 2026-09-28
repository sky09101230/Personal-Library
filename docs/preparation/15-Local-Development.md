# 本地运行准备

使用 Python 3.13、项目 `.venv` 和现有 requirements.txt。无需新增存储依赖，数据库使用项目已有的 SQLite 支持。

验收条件：数据库迁移及 Django 检查通过；文献、解析产物、Skill 正式文件及候选分别存储在本地；上传、流式下载、删除、移动与目录越界保护通过测试；本机 HTTP 页面可访问。

必需配置：本地 `.env` 中的随机 DJANGO_SECRET_KEY、SQLite、本地存储，以及管理员账号。执行 `start.ps1` 时会检查 `MINERU_API_TOKEN`，自动启动一个本地文献 worker；没有 token 时只启动网页并提示。可选服务密钥按功能启用，见 README。

## Personal 前端标识

复用现有 Django 模板和 CSS，无新增依赖。验收：登录、首页、文献、上传、Skills 和管理后台呈现 Personal 标识与暗绿色主色；模板中不再残留 PLAB 品牌及紫色主题；主要页面响应正常。
