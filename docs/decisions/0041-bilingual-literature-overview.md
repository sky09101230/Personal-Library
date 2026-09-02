# 0041 文献 Overview 以英文分析为源并保存中文翻译

## 决策

`plab.overview.v2` 的顶层 `summary_short`、`summary`、`topics` 和 `key_points` 保存英文文献理解结果；新增 `chinese_translation`，保存这些字段的简体中文 AI 翻译。中文关键点必须与英文关键点数量一致，并逐条复用完全相同的 chunk/page evidence。生成器在同一次结构化请求中先形成英文结果，再翻译为中文，避免两种语言成为证据可能分叉的两次独立分析。

文献详情默认展示英文，在 Overview 右上角提供 `English / 中文` 分段切换。切换只改变分析文本和引用标签，不改变 provider、model、prompt version、原始 PDF 或 Parsed Text。

## 版本与兼容性

Prompt 升级为 `overview-v2`，Overview schema 升级为 `plab.overview.v2`。版本变化会让后续重处理追加新的 job/parse/analysis，旧成功结果不会被覆盖。现有 v1 单语 payload 继续通过校验并按原样展示，但由于没有可信的英文源与中文翻译对，页面不为其显示语言切换；需要双语结果时按既有非破坏性重处理流程生成 v2。

## 理由

英文结果作为唯一分析源，中文明确作为翻译，可以区分“文献理解”和“面向中文阅读的辅助版本”。对双语 evidence 做一致性校验，保证任一语言中的结论仍能追溯到同一文献片段与页码，同时不修改原始科研资料或书目元数据。
