## 1. 架构与模型基础

- [x] 1.1 在 `docs/decisions/` 记录 App 边界、依赖方向、数据与 artifact 位置以及 Phase 1 non-goals
- [x] 1.2 创建 `apps.literature_processing`、注册 App，并实现四类模型及管理后台只读入口
- [x] 1.3 生成纯新增迁移，并用模型/约束测试验证 chunk 追溯和非破坏性版本关系
- [x] 1.4 验证 SQLite migration/check，静态检查迁移不含 PostgreSQL 不兼容 SQL

## 2. Parser Contract 与 Chunking

- [x] 2.1 实现版本化 PLAB 中立 parser contract 和 parser registry/adapter 边界
- [x] 2.2 实现 PyPDF fallback，保留页序、空页并清理数据库不兼容字符
- [x] 2.3 实现完整中立 parse artifact 的不可覆盖对象存储写入与索引
- [x] 2.4 实现确定性页内 chunking 和 parse/chunk 持久化服务
- [x] 2.5 测试多页/空页保留、parser 隔离、稳定 chunk 边界及完整追溯链

## 3. Processing Queue、Worker 与 Backfill

- [x] 3.1 实现版本感知且并发安全的 enqueue 与强制追加重处理语义
- [x] 3.2 实现数据库 claim、分阶段 pipeline、成功/失败状态和 management command worker
- [x] 3.3 在新 App 内通过 transaction-on-commit signal 安全 enqueue 新主 PDF
- [x] 3.4 实现有界历史主 PDF backfill management command
- [x] 3.5 测试成功/失败、上传失败隔离、重复 enqueue、重处理、worker 继续执行及 backfill 幂等

## 4. AI Overview 与 Evidence

- [x] 4.1 实现领域无关 Overview prompt/provider contract 和结构化响应解析
- [x] 4.2 在 `DocumentAnalysis` 持久化边界实现 overview schema 与 chunk/page evidence 校验
- [x] 4.3 将 overview 阶段接入 processing pipeline，记录 provider/model/prompt version 和输入指纹
- [x] 4.4 测试合法 Overview、跨 parse/不存在 chunk、错误 page、provider 失败及原 abstract 不变

## 5. 文献详情 UI

- [x] 5.1 由新 App 提供详情投影/路由组合，避免 `apps.box_upload` Python 代码反向依赖
- [x] 5.2 在现有文献详情体验展示 processing 状态、AI Overview、Parsed Text 和 PDF evidence 页码链接
- [x] 5.3 测试已完成、排队/失败、无处理结果和登录保护等页面状态

## 6. 最终验证与文档

- [x] 6.1 运行新 App、box_upload 回归及项目全量相关测试，并执行 `makemigrations --check`、`check` 和严格 OpenSpec 校验
- [x] 6.2 审计依赖方向与 Phase 1 non-goals，记录已知限制和 Phase 2 仅基于 `LiteratureChunk` 的接入边界
