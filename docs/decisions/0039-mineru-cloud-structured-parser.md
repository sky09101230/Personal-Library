# 0039 MinerU 云端结构化 parser

## 决策

在 `apps.literature_processing` 内增加 MinerU 官方精准解析 API v4 adapter，作为显式 opt-in 的 structured parser；PyPDF 和 `page-chars-v2` 继续作为生产默认与 fallback，真实样本验收前不切换全局默认。网络调用与 schema 转换分离：MinerU client 只负责 token、预签名上传、批量任务轮询、结果下载和 API 错误归一化；MinerU adapter 只负责结构化 JSON 到 PLAB `ParsedDocument` 的转换，两者都不依赖 Django 文献模型。

本地 NAS PDF 使用官方 `POST /api/v4/file-urls/batch` 申请预签名 URL，以无认证 `PUT` 上传文件，再轮询 `GET /api/v4/extract-results/batch/{batch_id}`。请求使用官方推荐的 `vlm` model version，并开启公式和表格识别。MinerU token 只从环境读取，不进入 job、artifact、日志或数据库。

PLAB normalized source-of-truth 优先使用稳定的 `*_content_list.json`。官方当前仍将 `*_content_list_v2.json` 标记为 development/subject to change，因此仅在 legacy content list 缺失时兼容读取并记录 warning；`middle.json`、v2、Markdown、图片和其他返回文件完整保存在 raw result bundle，但 downstream 不直接依赖这些 MinerU schema，也不以 Markdown 生成 chunks。

`plab.parse.v2` 以 page -> ordered blocks 表达 heading、paragraph、table、figure、figure caption、equation、list、code、reference、header、footer 和 unknown。block 保存稳定 id、页码、reading order、通用 bbox、heading level、结构化内容和 provider provenance。header/footer/page number 保留在 normalized parse 与 raw artifact 中，但 structure-aware chunker 默认排除；table 保持原子结构，equation 与相邻正文在尺寸允许时共同成块。PyPDF fallback 仍输出 page text 并使用 `page-chars-v2`。

## 长文分段

官方精准 API 当前限制单文件 200 MB、单任务 200 页。PLAB 在本地用 PyPDF 只读取页数，将超过 200 页的文档划分为连续 `page_ranges`；例如 585 页为 `1-200`、`201-400`、`401-585`。每个 segment 使用同一源 PDF 的独立预签名上传项，结果按 segment 起始页、page index 和 reading order 合并成一个 PLAB document。segment/task 信息只进入 raw manifest 和 `DocumentParse.runtime_info`，不泄漏给 chunks。

## Artifact 与数据模型

现有 `DocumentParse.artifact_*` 继续指向 PLAB normalized JSON。新增 raw artifact 索引指向同一 `Literature/derived/parses/` namespace 下的 MinerU bundle ZIP；bundle 包含无 secret manifest 和每个 segment 的官方结果 ZIP。数据库额外保存 actual parser、model/version、task ids、runtime、warnings 和 raw checksum。重处理保持 append-only，任何 API、下载、转换、artifact 或 Overview 失败都不修改原 PDF、bibliographic metadata 或既有成功 parse。

## 理由

真实 Docling CPU 验收显示本地模型成本高且收益不足；MinerU 云 API 可以把版面、公式和表格推理移出 worker，同时官方 content list 已提供 page、bbox、reading order 和通用内容类型。保持 provider-neutral v2 schema 和 raw/normalized 双 artifact，可在 MinerU schema 演进时重新转换，而不迫使 chunk、Overview 或未来检索代码理解 MinerU 私有格式。

## 非目标

本阶段不实现 MinerU 本地模型、Docling、embedding、pgvector、semantic/hybrid retrieval、RAG、reranker、Knowledge Graph、领域 ontology、GLM deep analysis 或全量 629 篇重处理。现有 Overview provider 不做大规模重构。

## 官方依据

- MinerU API 文档：`https://mineru.net/apiManage/docs`（2026-09-01 核对）
- MinerU output files：`https://opendatalab.github.io/MinerU/reference/output_files/`
- `content_list_v2` 官方说明仍标记为 development，因此本阶段不把它设为首选合同。
