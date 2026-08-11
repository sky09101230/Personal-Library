# 0013 使用 WhiteNoise 提供静态文件

## 决策

Uvicorn 继续承载项目的 ASGI 应用和 MCP 路由；Django 静态文件由 WhiteNoise 中间件提供。部署时必须先执行 `python manage.py collectstatic --noinput`，将文件收集到不进入版本控制的 `staticfiles/`。

## 理由

Uvicorn 不会自动提供 Django Admin 的 `/static/` 资源，而改用 `runserver` 会绕开现有 ASGI 部署方式。WhiteNoise 能在不增加独立反向代理的情况下补齐当前单机部署所需的静态文件服务。

## 约束

- WhiteNoise 中间件紧跟在 `SecurityMiddleware` 后。
- `STATIC_ROOT` 仅保存部署生成物，不得提交到仓库。
- 每次更新依赖或静态资源后重新运行 `collectstatic` 并验证 Admin CSS 返回 HTTP 200。
