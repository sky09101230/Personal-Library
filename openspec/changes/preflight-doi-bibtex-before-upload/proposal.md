## Why

上传流程当前会先写入 NAS，再通过 DOI 请求 BibTeX；网络失败会留下已经上传但 metadata 获取失败的文献。上传前应先确认该批次所需的 DOI/BibTeX 请求能够成功，避免产生部分完成状态。

## What Changes

- 在向 NAS 写入任何文件前，扫描本批次 PDF 的 DOI，并完成所需 BibTeX 请求预检。
- 复用预检得到的 BibTeX，避免上传后重复请求。
- 预检失败时停止整个批次，通过 AJAX 返回明确错误，并在浏览器弹窗提示。
- 无 DOI 的 PDF 不触发 DOI/BibTeX 网络预检。

## Capabilities

### New Capabilities

- `doi-bibtex-upload-preflight`: 约束 DOI/BibTeX 预检、批次阻断和用户错误提示行为。

### Modified Capabilities

无。

## Impact

影响文献上传视图、上传页面 JavaScript 和上传测试；不新增依赖，不改变 NAS 存储接口。
