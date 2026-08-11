# MCP 服务依赖准备

## 运行时依赖

- Python 3.12
- Django 5.1.7
- `mcp`：官方 Python MCP SDK，用于提供 Streamable HTTP MCP 传输与工具协议。

## 部署前配置

在 `.env` 中设置实际对外地址和上传上限：

```dotenv
MCP_PUBLIC_BASE_URL=https://library.example.edu
MCP_MAX_UPLOAD_BYTES=20971520
```

管理员在 Django 后台创建访问令牌并仅通过安全渠道发送给使用者。用户在自己的 Codex MCP 配置中使用 `Authorization: Bearer <token>` 请求头连接 `${MCP_PUBLIC_BASE_URL}/mcp`。

生产环境需要 ASGI 服务（例如 Uvicorn）和反向代理提供 TLS；应用本身不管理 TLS 私钥。

## 启动与连接

完成迁移后，使用 ASGI 而不是 Django 开发服务器启动服务：

```powershell
python manage.py migrate
uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

在管理员后台的 `MCP 服务 > MCP 访问令牌` 创建令牌。新建成功页面只会显示一次明文令牌；管理员可通过停用令牌立即撤销访问。

使用者将令牌保存在自己的环境变量中，并在其 Codex 配置加入：

```toml
[mcp_servers.plab_library]
url = "https://library.example.edu/mcp"
bearer_token_env_var = "PLAB_MCP_TOKEN"
```

`PLAB_MCP_TOKEN` 的值是管理员签发的令牌。反向代理必须将外部域名原样传递为 `Host` 请求头，否则 MCP 的主机校验会拒绝该请求。
