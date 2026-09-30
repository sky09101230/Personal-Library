# README 安装与配置整理

日期：2026-09-30。当前任务为整理启动说明并推送已有提交。

README 按基础启动、模型接口、MinerU/PyPDF、可选服务、停止/更新/备份和排错组织，配置名与当前代码对照。保留真实 .env、数据库、论文、日志和截图于本机；不重新生成密钥或搬迁资料。

编码/部署依赖：启动脚本直接使用 Uvicorn，之前依赖其间接安装。现在将本地已验证版本 uvicorn==0.54.0 显式列入 requirements.txt，无新服务或框架。模板默认 PAPER_LLM_BASE_URL 留空，避免首次复制后误启用不完整 provider；补齐当前 Skeleton 的输出和 fallback 参数，不更改真实配置。

验收：README 步骤与 CLI 实参对应；基础默认 profile 可禁用 AI，已填 provider 参数完整；模板参数在说明中可查；Markdown 本地链接存在；依赖安装检查、Django/迁移与全仓测试、OpenSpec strict 通过；暂存文件与待推送历史不含真实密钥/科研资料；提交后普通快进推送并核对远端 HEAD 与工作区状态。
