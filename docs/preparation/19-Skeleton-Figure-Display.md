# Skeleton 图示解读的图片展示

日期：2026-09-30。无新增依赖或模型迁移，复用 parse-local EvidenceCatalog 和鉴权 Figure asset endpoint。

验收：每条 Figure 解读展示对应原图、原文 Fig 标签、图注和 PDF 页入口，点击图片可放大；同一真实图注关联的拆分子图成组展示。缺图或失效来源显示提示，不能猜图号或读取客户端给出的路径。图片读取保留登录、发布状态、parse 隔离、private/no-store 与 nosniff。

显示默认依据保存的 Figure Evidence ID；如果旧记录的 Figure ID 与唯一的引用图注冲突，只使用同 parse 中确实关联该图注的 Figure 展示，并显示来源纠正说明，不改写旧 payload 或 Evidence 身份。图片使用 lazy loading，读取失败时显示 PDF 回退。按原文标签命名标题，不用列表序号假扮 Fig 编号。

回归包含旧 Figure ID/图注不一致、拆分子图、图片端点登录/跨 parse/撤销发布控制。真实文献 12 使用已有解析资产读取验证，无调用 LLM、无复制或改写原始科研资料。

验证结果：详情页回归 13/13 通过，Django check/无迁移检查通过；真实文献 12 共 10 张去重图片均 HTTP 200，内嵌 JavaScript 语法通过。在临时本地服务和真实浏览器中确认 Fig. 1 图片、解读、图注和 PDF 入口显示正常；验证截图留在忽略目录 .runtime，不提交科研图片。
