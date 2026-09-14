## Why

正式 Skill 列表目前只显示来源名称，用户无法直接回到上游 GitHub；详情页也只能看到摘要、提交号和下载包，无法快速判断发布包内有哪些说明、参考资料或代码。补充来源链接和受控文件预览，可以让网页端完成基本的溯源与阅读闭环。

## What Changes

- 在 Skills 列表的来源名称上直接链接到对应 GitHub 仓库。
- 在 Skill 详情页展示当前正式发布包的文件列表，并默认预览 `SKILL.md`。
- 支持通过详情页选择文本、Markdown、配置和代码文件进行预览；代码按文件名识别语言并进行语法高亮。
- 对二进制、无法按 UTF-8 解码或超过预览上限的文件显示不可预览提示，不改变原始发布包。
- 预览只读取正式 release 的 NAS 包，不暴露候选存储路径，不改变下载和 MCP 边界。

## Capabilities

### New Capabilities

- `skill-source-and-file-preview`: 展示正式 Skill 的 GitHub 来源链接与发布包文件预览。

### Modified Capabilities

无。现有候选审核和正式发布规则保持不变。

## Impact

- `apps/skills`：新增发布包预览读取逻辑、详情上下文和测试。
- `templates/skills`、`templates/base.html`：来源链接、文件树和高亮代码展示。
- `requirements.txt`：增加服务端语法高亮依赖 Pygments。
- 不新增存储后端，不修改现有发布包内容。
