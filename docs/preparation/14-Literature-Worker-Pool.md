# Literature worker pool 准备与验收

## Token 布局

```text
MINERU_REALTIME_API_TOKEN=
MINERU_BACKFILL_API_TOKEN_1=
MINERU_BACKFILL_API_TOKEN_2=
MINERU_BACKFILL_API_TOKEN_3=
MINERU_BACKFILL_API_TOKEN_4=
```

如果 `MINERU_REALTIME_API_TOKEN` 为空，realtime channel 兼容读取现有 `MINERU_API_TOKEN`。worker pool 要求 1+4 个 token 全部非空且互不相同；校验和日志不得输出 token 值。

## 运行方式

```powershell
python manage.py plab literature worker-pool
```

单 channel 调试仍可使用：

```powershell
python manage.py plab literature worker --lane realtime --token-slot realtime --once
python manage.py plab literature worker --lane backfill --token-slot 1 --once
```

历史文献只 enqueue，不在 Web 请求内处理：

```powershell
python manage.py plab literature backfill --parser mineru --lane backfill --limit 100
```

## 验收条件

1. 新主 PDF 在上传事务提交后自动创建 `mineru + realtime` job；callback 只写数据库且失败不影响 upload。
2. realtime/backfill claim 相互隔离；PostgreSQL 使用 `skip_locked`，SQLite 单 worker 测试保持通过。
3. 5-channel pool 使用 5 个独立 token context 和独立 Django thread connection，数据库不保存 token。
4. MinerU progress callback 汇总 segmented pages，provider batch id、state、current/total/unit 和 heartbeat 可查询。
5. 登录用户可以 polling 文献状态 JSON；未登录拒绝，终态停止 polling，页面无需刷新即可显示成功/失败。
6. 旧 CLI 保持兼容；backfill/process-existing 可显式选择 MinerU/backfill lane。
7. 上传、job 失败、重复 enqueue、并发 claim、pool token 配置、status endpoint、SQLite 和 PostgreSQL migration 均有覆盖。

