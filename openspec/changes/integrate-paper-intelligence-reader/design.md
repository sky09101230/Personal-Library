# Paper Intelligence 阅读器集成

## Context

详情模板已有 Overview 双语切换、PDF 新窗 #page 链接与隐藏 details 下的 chunk 锚点；无图预览。原生浏览器 viewer 支持页跳转意图，但不提供本项目控制的精确 bbox overlay。

## Decisions

1. 页面基于 B 的明确 active parse 组织四区：Paper Overview、Paper Chat、Parsed Content、PDF。显示 parse/parser/schema 的简要出处与旧版本标签。保留 processing 状态，分析失败不能遮住 PDF 和 Parsed Content。
2. Overview 优先当前 parse 的新 Skeleton；无结果显示生成入口及旧 Overview（若旧结果属其它 parse 必须带版本标签和旧来源 URL）。旧 English/中文功能保留，不将旧裸 summary 假装为新逐 claim 格式。
3. Chat UI owner-only，会话选择和消息分页遵从 D。发送按钮显示 pending/busy/failure，重复点击使用同 request_id；不渲染未验证 token。stale_parse 后明确提供新会话入口，旧会话只读；不能自动复制旧问答到新会话。
4. Evidence chip 仅接受服务端验证后的 display DTO：kind、页、section、原文、同源 URL。Source panel 可显示 Figure、caption、mentions、table/equation 原文；无图或无 chunk 也有文字与 PDF 页回退。旧 Overview 的 chunk/page 显示适配先运行旧 validator，不能替旧 payload补造 ID。
5. 点击 chunk 时展开父 details 并 focus/scroll；同页与跨页锚点包含 parse identity。历史来源读取必须显式 parse_id，而不是指向只显示 active parse 的当前详情 anchor。链接打开 source panel 的同 parse 内容，PDF 始终为该 parse 的 source upload。
6. Figure HTTP GET 只接受 parse_id + evidence_id，调用 B 授权与 resolver，不接受 path 参数。返回 private,no-store + nosniff、限定 image MIME；错误安全且可回退，不暴露 raw bundle 地址。Body/asset 读取与生成在访问时都重查 published。
7. 模型内容默认纯文本、模板自动转义；若 Markdown，只允许本地受限渲染，禁 raw HTML/远程媒体/可执行链接。Table HTML 原文按文本显示，不直接 safe。任何原始/生成字段不得拼进 innerHTML。
8. 写操作 POST+CSRF，GET 仅读取；匿名跳登录，越权 conversation 返回不可访问。未发布文献新智能区不可用，保留已有人工审核页面，不让它们绕到模型生成。
9. 使用项目原生 Django/CSS 与小段 JS；无 JS 仍能读已有分析及 source 链接。tabs、Evidence、source panel 均可键盘触发，状态 aria-live，移动窄屏无水平内容丢失。
10. F 不改变 PDF streaming/Range 实现，PDF #page 在浏览器不生效时仍显示真实页号供手动定位；没有 bbox 的来源不显示虚假高亮。

## Acceptance and Compatibility

当前 parse、历史 parse、纯 PyPDF、旧 Overview v1/v2、缺图/无结果/生成失败皆有清晰 UI；通过实际浏览器从一个 claim 到图/caption/chunk/PDF 页的闭环。相关 Python view 测试不能替代浏览器导航和可访问性检查。

## Risks

原生 PDF 查看器行为依浏览器差异，验收“链接/页码正确且能打开来源”，精确高亮不在 V1。旧详情允许登录用户查看未发布 metadata，不扩大到智能生成；发布门禁由 B 独占逻辑。

## Goals / Non-Goals

目标：在现有 Django 详情页组合 Overview、Chat、Parsed Content、PDF，并让所有 Evidence 能回到同一版本真实来源。

非目标：不实现新的 PDF.js/bbox 标注器，不创建 SPA，不重新实现 provider/retrieval/validator，不公开原始存储目录或新增 MCP 工具。

## Dependencies and Ownership

依赖 A/B/C/D/E；直接消费 B 的来源、D 的对话服务与 E 的分析服务，作为最后一个集成 Change。

受影响模块：apps/literature_processing/views.py/urls.py、templates/literature_processing/detail.html、新 _paper_evidence.html 及局部静态样式/脚本；组合 chat_urls/skeleton_urls；新增 reader_views.py 或 evidence 视图及 test_paper_reader.py；复用 apps/box_upload PDF stream。

## Migration Plan

无数据库迁移；新功能开关可关闭，原 PDF/旧 Overview 路径保留。无新结果时可读旧版本；旧 evidence 只作安全显示适配，不写回旧 payload。回滚关闭新入口并保留 Chat/Skeleton 数据。

## Acceptance Criteria

必须通过本 Change 全部 spec 场景、对应测试和 strict validation。真实 provider、PostgreSQL 和语义评测未验证项单独报告；本轮不实施。公共契约遵循 [0045](../../../docs/decisions/0045-paper-intelligence-v1.md)。
