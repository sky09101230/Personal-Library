# MCP 服务依赖准备

## 运行时依赖

- Python 3.14
- Django 5.2.17
- `mcp==1.26.0`：官方 Python MCP SDK，用于提供 Streamable HTTP MCP 传输与工具协议。

## 部署前配置

在 `.env` 中设置实际对外地址和上传上限：

```dotenv
MCP_PUBLIC_BASE_URL=https://library.example.edu
MCP_MAX_UPLOAD_BYTES=104857600
```

管理员在 Django 后台创建访问令牌并仅通过安全渠道发送给使用者。用户在自己的 Codex MCP 配置中使用 `Authorization: Bearer <token>` 请求头连接 `${MCP_PUBLIC_BASE_URL}/mcp`。

`/mcp` 挂载在项目的 ASGI 应用中，生产环境必须使用 Uvicorn 等 ASGI 服务，不能改用只承载 WSGI 的进程。应用本身不管理 TLS 私钥。

## 启动与连接

完成迁移后，使用 ASGI 而不是 Django 开发服务器启动服务：

```powershell
python manage.py migrate
uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

端口 `8000` 只绑定 `127.0.0.1`，不得直接暴露到局域网或互联网。外部访问统一经过反向代理，由反向代理终止 TLS，并把原始 `Host` 与 `Authorization` 请求头传给 Uvicorn。

在管理员后台的 `MCP 服务 > MCP 访问令牌` 创建令牌。新建成功页面只会显示一次明文令牌；管理员可通过停用令牌立即撤销访问。

使用者将令牌保存在自己的环境变量中，并在其 Codex 配置加入：

```toml
[mcp_servers.plab_library]
url = "https://library.example.edu/mcp"
bearer_token_env_var = "PLAB_MCP_TOKEN"
```

`PLAB_MCP_TOKEN` 的值是管理员签发的令牌。`MCP_PUBLIC_BASE_URL`、TLS 证书域名和反向代理传入的 `Host` 必须一致，否则 MCP 的主机校验会拒绝请求。
