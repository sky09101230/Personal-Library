# 页内阅读 Tab 与空总览修复

日期：2026-09-29。复用 Django 模板、原生 JS 和现有 Provider，无新增依赖。

验收：顶部 Tab 默认智能阅读，支持键盘与 chunk 深链切换；旧 Overview/原文仍可读。旧空 Skeleton 不再展示八个误导性的“证据不足”，保留原行并允许重新生成。新请求必须覆盖非空章节及图注，记录真实预算/覆盖，模型格式不合法或全空不能保存为成功。真实论文必须得到有来源的有效内容。

根因：旧生成器固定 budget=1000，context builder 的 per_bucket 没有使用；遍历首桶耗尽预算且 Figure 永不入选。旧 sanitizer 将错误结构清成空 claims，再保存成功并缓存。旧 UI 也没有重新生成入口。

修复：Skeleton v2 用完整 source item 按章节轮取并先保留每个章节与图注，正文/图都进入 allowlist；以序列化 UTF-8 字节限制输入，预算不足明确失败，不切断原文。跳过参考文献/版权页，Results and discussions 正确归 Results。删除静默清空逻辑，使用明确中文 claim schema 与严格校验；零有效结论为 failed，旧数据不删除。prompt 版本升级使旧空缓存失效。总览独立 timeout 默认 120 秒、无 transport retry，未影响 Chat 超时。增加顶部 Tab、中文章节标签、加载/错误/重新生成和图示解读显示。

SQLite 本机真实 parse 14 验证：62 条完整输入来源，含全部 11 个 Figure 条目，覆盖 Abstract/Introduction/Method/Results/Conclusion；45,822 UTF-8 字节。一次真实调用成功得到 11 条章节 claims、5 个图示解读条目，analysis 18，耗时 85.3 秒。真实资料与模型输出仍仅留本机数据库，未加入 Git。模型字段原本为空，补全为此前接口已验证的 gpt-6-luna；认证密钥未变、未输出。

自动验证包括尾页 Conclusion/尾图预算、全空/非法输出拒绝、非法引用保留旧结果、force 追加、旧空结果按钮及详情页回归。浏览器连接工具当前不可用，不能声称已完成真实浏览器视觉验收；使用 Django 渲染与 JS 语法检查，并在最终回复说明重启和刷新要求。
