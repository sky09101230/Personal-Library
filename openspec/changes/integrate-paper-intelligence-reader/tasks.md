## 1. 页面组合

- [x] 1.1 用 B active parse 选择更新详情上下文，保留旧 Overview v1/v2 与处理状态。
- [x] 1.2 组合 D/E 独立路由并加入四区布局、生成/会话操作及状态展示。

## 2. 证据交互

- [x] 2.1 实现公共 Evidence 模板与 source panel，chunk 展开/focus、历史 parse 路由、figure/caption/section/PDF 导航。
- [x] 2.2 实现仅 parse/evidence 参数的受控图片 GET，复用 B 并设置 private/no-store/nosniff。

## 3. 权限与回退

- [x] 3.1 覆盖 owner/published/CSRF、安全文本、旧结果/无图/无 parse/模型不可用/过期会话状态。
- [x] 3.2 保留无 JS 阅读、键盘/aria-live、窄屏与原 PDF viewer fallback。

## 4. 验收

- [x] 4.1 添加 reader 详情回归、版本来源和旧 Overview 回归测试。
- [x] 4.2 完成服务/API 级闭环；浏览器视觉/键盘窄屏复核留到真实启动环境。
- [x] 4.3 运行相关 Django/迁移/PDF Range/MCP 回归与全六项 strict validation，记录真实论文和 PostgreSQL 未实测项。
