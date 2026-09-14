## Context

`SharedSkill` 已保存 GitHub 来源和源路径，`SharedSkillRelease` 保存正式 NAS 压缩包路径；现有详情页只展示元数据并提供下载。候选包位于独立存储，不能被详情页读取。项目没有前端语法高亮依赖，运行环境已提供 Pygments，因此采用服务端生成高亮 HTML。

## Goals / Non-Goals

**Goals:**

- 复用 `repository_url` 作为列表来源链接，保持用户投稿来源为纯文本。
- 使用正式 release 的现有流读取接口构建有界 ZIP 预览。
- 在服务端完成文件名到语言的识别和 HTML 转义，模板只负责展示。

**Non-Goals:**

- 不提供在线编辑、文件上传、候选包预览、Markdown 渲染或整包解压到持久目录。
- 不在浏览器端引入 CDN、JavaScript 代码编辑器或新的前端框架。

## Decisions

- 新增 `apps.skills.previews` 模块，使用 `SpooledTemporaryFile` 将 release 流临时落盘，再用 `zipfile` 读取文件名和有限内容；默认 256 KiB 单文件预览上限，避免把 800 MiB 发布包或单个大文件全部载入内存。
- 文件选择通过详情页的 `?file=` 查询参数完成；只接受 ZIP 中精确存在的相对路径，默认优先 `SKILL.md`，无需新增预览 API。
- Pygments 使用 `get_lexer_for_filename` 按扩展名选择 lexer，`HtmlFormatter` 输出已转义的高亮片段；未知文本回退为转义后的纯文本，缺失依赖视为部署错误而不是静默输出不安全 HTML。
- 预览读取异常沿用现有存储错误边界，仅向页面返回通用提示；下载接口保持原有流式行为。

## Risks / Trade-offs

- [Risk] 每次详情请求都读取并扫描 ZIP，远端包大时延迟增加 → 只读取当前详情页所需的 release，限制文件数量和单文件预览，后续若有性能数据再增加缓存。
- [Risk] Pygments lexer 对少见扩展名判断不准确 → 仍展示文件列表并回退纯文本，不阻断详情页。
- [Risk] 高亮 HTML 增加模板上下文复杂度 → 仅对 Pygments 自己生成的字符串使用 `mark_safe`，原始文件内容始终先经 lexer/转义。

## Migration Plan

无需数据库迁移；新增 Pygments 依赖后部署代码即可。旧 release 无需转换，无法读取的包只显示通用不可用提示。
