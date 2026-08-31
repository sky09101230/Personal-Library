## Context

当前上传视图在写入 NAS 并建立数据库记录后才解析 PDF DOI 和请求 BibTeX。上传页面通过单个 AJAX 请求提交整个批次，因此服务端可以在产生存储副作用前完成真实请求预检。

## Goals / Non-Goals

**Goals:**
- 批次内所有 DOI/BibTeX 请求先于任何 NAS 写入。
- 复用预检结果，避免上传后再次请求同一 BibTeX。
- 保持无 DOI、重复内容和 Crossref 补全的既有行为。

**Non-Goals:**
- 不新增独立健康检查端点或后台任务。
- 不把 Crossref 可用性纳入上传阻断条件。
- 不改变 NAS 存储协议或数据模型。

## Decisions

1. 使用实际 BibTeX 获取作为预检，而不是额外 ping。ping 成功不能保证真实请求成功；实际请求同时验证网络、HTTP 响应和 BibTeX 格式。
2. 服务端先计算批次摘要并扫描新内容的 DOI，缓存每个摘要对应的 BibTeX，再进入现有存储循环。同一内容在批次内只预检一次。
3. 将缓存的 BibTeX 通过现有 metadata resolver 注入点复用，避免第二次 DOI 请求。Crossref 仍按现有容错规则运行。
4. 后端返回 400 JSON 作为强制边界，前端在现有 XHR 错误分支增加弹窗；不依赖仅前端的连通性检查。

## Risks / Trade-offs

- [大 PDF 会在写入 NAS 前被额外扫描一次] → 仅扫描现有 metadata 逻辑使用的有限页面，且不增加依赖。
- [DOI 存在但服务返回无效记录时也会阻断] → 错误信息描述为 DOI/BibTeX 预检失败，用户修复网络或文献 DOI 后重试。
- [预检增加上传开始前延迟] → 每个唯一新内容只请求一次，并复用结果。

## Migration Plan

部署代码后无需数据迁移。若需回滚，恢复上传视图的原执行顺序和前端错误展示即可。
