## Purpose

让用户在 Skills 广场中能够追溯正式 Skill 的上游仓库，并在不下载整个压缩包的情况下检查其已发布文件和代码内容。

## ADDED Requirements

### Requirement: Source links identify the upstream repository

系统 SHALL 在有 GitHub 来源的 Skill 列表卡片中，将来源名称链接到该来源保存的仓库 URL，并在新窗口打开且使用安全的外链属性；无 GitHub 来源的用户投稿不得伪造仓库链接。

#### Scenario: GitHub source is linked
- **WHEN** 用户查看带有 GitHub 来源的正式 Skill 列表
- **THEN** 来源名称本身是指向该仓库 URL 的外链

#### Scenario: User submission has no repository link
- **WHEN** 用户查看没有 GitHub 来源的正式 Skill 列表
- **THEN** 页面显示用户投稿来源文本，不渲染 GitHub 链接

### Requirement: Detail page exposes formal release files

系统 SHALL 在详情页展示当前首选正式 release 中的非目录文件列表，并允许用户选择文件查看内容；默认选择 `SKILL.md`（存在时）或第一个可预览文本文件。

#### Scenario: Release file tree is available
- **WHEN** 正式 Skill 存在可读取的 release
- **THEN** 详情页展示相对文件路径、文件大小和可选择的文件项

#### Scenario: Release is unavailable
- **WHEN** Skill 没有正式 release 或存储读取失败
- **THEN** 详情页保留现有摘要和下载信息，并显示文件预览暂不可用，不泄露存储异常细节

### Requirement: Text and code previews are bounded and highlighted

系统 MUST 只预览受支持的文本内容并限制单文件读取大小；代码文件 SHALL 根据文件名识别语言并返回语法高亮结果。无法识别、无法 UTF-8 解码、包含二进制内容或超过上限的文件 MUST 不直接输出原始内容。

#### Scenario: Code file is highlighted
- **WHEN** 用户选择 `.py`、`.js` 或其他可识别代码文件
- **THEN** 页面以对应语言的高亮 HTML 展示其受限内容，并保留等宽代码布局

#### Scenario: Unsafe or oversized file is not previewed
- **WHEN** 用户选择二进制、无法解码或超过预览上限的文件
- **THEN** 页面显示不可预览原因，不读取或渲染超出上限的内容

### Requirement: Preview preserves publication boundaries

系统 MUST 只从正式 `SharedSkillRelease` 读取预览；预览请求不得访问候选包、修改 NAS 对象或使未发布内容进入 Discover、MCP 或其他用户上下文。

#### Scenario: Candidate content remains isolated
- **WHEN** 候选记录尚未发布
- **THEN** 其文件不会出现在正式 Skill 详情页的文件列表或预览中
