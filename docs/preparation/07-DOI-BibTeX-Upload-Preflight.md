# DOI BibTeX 上传前预检准备

## 目标链路

上传请求先计算批次内每个 PDF 的摘要。对数据库中尚不存在的唯一内容提取 DOI；发现 DOI 时立即请求并验证 BibTeX。全部预检成功后才进入现有 NAS 写入循环，并把已取得的 BibTeX 传给 metadata resolver 复用。

## 依赖与配置

不新增依赖或配置。继续使用：

```dotenv
DOI_RESOLVER_URL=https://doi.org
METADATA_HTTP_TIMEOUT=5
```

## 失败边界

- 网络、超时、HTTP 或 BibTeX 响应验证失败：整批停止，NAS 与上传数据库均不写入。
- PDF 无 DOI：跳过预检并继续上传。
- 内容已存在：不重复执行新记录的 DOI/BibTeX 预检。
- Crossref 失败：沿用现有 metadata 容错，不影响已通过的上传。

## 验收

- 失败测试证明存储函数未调用且上传记录数为零。
- 成功测试证明预检 BibTeX 在 metadata 解析中复用。
- 无 DOI 测试证明不触发网络预检。
- 浏览器测试证明失败弹窗出现、页面不跳转且按钮恢复可用。
