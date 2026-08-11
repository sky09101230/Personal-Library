# 0007 远程 MCP 文献与 Skill 访问

## 决策

为需要访问本站资料库的外部 Codex 提供独立的远程 Streamable HTTP MCP 服务。服务只暴露检索、元数据读取、下载链接获取和文献上传这四类必要能力；网页端既有的 Django Session 登录流程保持不变。

访问使用由站点管理员创建并一次性展示的 Bearer API Token。令牌仅保存 SHA-256 摘要，并以最小权限范围限制工具调用：`literature:read`、`literature:write` 与 `skills:read`。不把 NJU Box 密钥、资料库密码或 Django 用户密码交给 MCP 客户端。

上传采取 MCP 工具的 Base64 载荷，限定为 PDF 且默认最大 20 MiB；这覆盖普通论文文件并使请求有明确的完整性边界。更大文件的直传协议留待实际需求出现后再增加。

## 理由

外部 Codex 无法访问服务器上的本地文件路径，因此本机 stdio 服务不能满足共享资料库的目标。管理员签发的 API Token 比一次性接入跨用户 OAuth 更适合当前私有科研组部署，同时服务端仍可撤销令牌并审计使用者。

## 约束

- 生产部署必须通过 HTTPS 暴露 MCP 端点，且不得把开发服务器直接公开到互联网。
- 下载工具只返回 NJU Box 生成的链接，不转存或代理原始文献与 Skill 压缩包。
- 所有写操作都必须拥有 `literature:write` 范围；上传文件只在成功写入 NJU Box 后创建数据库记录。
- API Token 明文只在新建时显示一次，不能从管理后台取回。
