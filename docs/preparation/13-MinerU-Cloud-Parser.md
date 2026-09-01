# MinerU 云端 parser 准备与验收

## 官方 API 合同

1. `POST https://mineru.net/api/v4/file-urls/batch`，Header 为 `Authorization: Bearer <token>`，body 包含 `files`、`model_version=vlm`、`enable_formula=true`、`enable_table=true`。
2. 每个 `files` item 包含带 `.pdf` 后缀的 `name`、PLAB 生成的 `data_id`、`is_ocr=false`，长文档额外包含连续 `page_ranges`。
3. 对返回的每个 `data.file_urls` 使用无 Authorization 的 `PUT` 上传 PDF bytes；HTTP 200 才视为成功。
4. 轮询 `GET /api/v4/extract-results/batch/{batch_id}`。`waiting-file/pending/running/converting` 继续等待，`done` 下载 `full_zip_url`，`failed` 转为安全的 provider error。
5. ZIP 默认包含 Markdown 和 JSON。normalized conversion 优先查找 `*_content_list.json`，只在缺失时读取 `*_content_list_v2.json` 并告警；绝不回退 Markdown。

## 配置

不增加本地 MinerU 或 HTTP framework 依赖，继续使用 Python 标准库和已有 PyPDF。配置全部来自环境：

```text
MINERU_API_BASE_URL=https://mineru.net/api/v4
MINERU_API_TOKEN=
MINERU_MODEL_VERSION=vlm
MINERU_REQUEST_TIMEOUT=120
MINERU_POLL_INTERVAL=5
MINERU_POLL_TIMEOUT=3600
MINERU_SEGMENT_PAGES=200
MINERU_RESULT_MAX_BYTES=536870912
```

token 在 `https://mineru.net/apiManage` 登录后自行创建。缺 token 时 Django 启动、PyPDF processing 和全部 fake 测试必须正常；只有显式调用 MinerU parser 才返回 `mineru_configuration`。

## 可验证验收条件

1. client fake 覆盖 allocation -> PUT -> poll -> ZIP download、HTTP/API error、timeout 和 result size limit。
2. legacy content list 转换不丢 page、bbox、type、heading level、reading order、table/equation/list/code/reference/header/footer；v2 fallback 有独立测试与 warning。
3. 585 页分为三个 segment，local/global `page_idx` 两种返回形式都合并为连续 1–585 页且 block id/order 稳定。
4. structure-aware chunks 排除 header/footer/page number，table 不拆分，长文本从词/句边界切分，source span 可回到 block/page。
5. normalized JSON 与 raw MinerU bundle 都写入 NAS `derived/parses` 并在 `DocumentParse` 保存 checksum/path/task metadata；数据库失败时 best-effort 清理本次两个 artifact。
6. MinerU failure 可安全 fallback PyPDF，processing failure 不影响 upload、原 PDF、原始 abstract 或 bibliographic metadata。
7. CLI 可对单个 upload 显式选择 `--parser mineru`，默认 enqueue/backfill/signal 仍使用 PyPDF。
8. `literature_processing`、全仓、migration drift、SQLite 和 PostgreSQL migration plan 通过。

## 真实 smoke

未配置 token 时不发送论文。配置后先从固定 10 篇中选择 3–5 篇、仅显式 force enqueue：

```powershell
python manage.py plab literature enqueue --upload-id <id> --parser mineru --force
python manage.py plab literature worker --once --max-jobs <count>
```

先覆盖 3 页公式文献、中文综述、双栏论文、表格/图像论文和中等长 tutorial。585 页专著只在短样本 API 合同与 quota 验证后运行 segmented smoke；不 backfill 其余历史文献。

