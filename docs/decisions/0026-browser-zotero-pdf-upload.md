# 0026 浏览器端 Zotero PDF 上传

## 决策

当网站运行在服务器 A、管理员从电脑 B 访问时，由 B 的浏览器通过现有 Zotero 导入请求上传本地 PDF。Collection 中每条文献显示独立文件框，字段名按 Zotero Item Key 绑定；服务器只处理同时出现在已选条目列表中的文件。

## 来源顺序

浏览器明确选择的 PDF 优先级最高；未选择时才使用服务器 A 上的 Zotero Desktop，最后回退 Zotero Web。浏览器文件失败时保留 metadata、继续后续条目并报告错误，不静默换用其他来源。

## 边界

不扫描 B 的文件系统，不按标题或文件名猜测匹配，不上传回 Zotero。每条文献一次只接收一个浏览器 PDF，继续跳过自动来源中的网页快照、URL 附件和 linked file。
