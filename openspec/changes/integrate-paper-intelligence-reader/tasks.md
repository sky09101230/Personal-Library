## 1. 页面组合

- [ ] 1.1 用 B active parse 选择更新详情上下文，保留旧 Overview v1/v2 与处理状态。
- [ ] 1.2 组合 D/E 独立路由并加入四区布局、生成/会话操作及状态展示。

## 2. 证据交互

- [ ] 2.1 实现公共 Evidence 模板与 source panel，chunk 展开/focus、历史 parse 路由、figure/caption/section/PDF 导航。
- [ ] 2.2 实现仅 parse/evidence 参数的受控图片 GET，复用 B 并设置 private/no-store/nosniff。

## 3. 权限与回退

- [ ] 3.1 覆盖 owner/published/CSRF、安全文本、旧结果/无图/无 parse/模型不可用/过期会话状态。
- [ ] 3.2 保留无 JS 阅读、键盘/aria-live、窄屏与原 PDF viewer fallback。

## 4. 验收

- [ ] 4.1 添加 reader 视图/模板权限、版本来源、恶意内容和旧 Overview 回归测试。
- [ ] 4.2 执行浏览器闭环：提问→claim→原文/图/caption→PDF 页；测试旧会话、新 parse 和键盘窄屏。
- [ ] 4.3 运行相关 Django/迁移/PDF Range/MCP 回归与全六项 strict validation，记录全仓既有失败和未实测环境。
