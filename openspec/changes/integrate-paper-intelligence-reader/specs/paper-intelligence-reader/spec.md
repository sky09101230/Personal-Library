## ADDED Requirements

### Requirement: 阅读器展示四类内容及版本
系统 MUST 在详情提供 Paper Overview、Paper Chat、Parsed Content、PDF，并明确当前 parse 与生成状态。

#### Scenario: 已生成新分析
- **WHEN** 当前 parse 有成功 Skeleton
- **THEN** 优先显示 Skeleton 及 evidence，Chat/Parsed Content/PDF 同时可达

#### Scenario: 旧数据或新生成失败
- **WHEN** 仅有旧 Overview v1/v2 或新模型失败
- **THEN** 保留旧阅读结果与 PDF，旧分析带其 parse 身份，失败不清空可用内容

### Requirement: Evidence 导航到同版本来源
系统 MUST 使用后端 display DTO 呈现 Evidence，并提供同 parse 的页、chunk、figure、caption、section 导航。

#### Scenario: 隐藏 chunk
- **WHEN** 用户点击位于折叠 details 中的 Evidence
- **THEN** 展开正确 parse 的片段、移动焦点并显示原文和 PDF 页入口

#### Scenario: 历史对话来源
- **WHEN** 用户点击旧 parse 消息的证据
- **THEN** 展示旧 parse 来源，不跳到当前 parse 的同名 chunk 或 figure

#### Scenario: 没有图片或 chunk
- **WHEN** Figure asset 缺失或无对应文本 chunk
- **THEN** 显示明确缺图状态与可用 caption/PDF 页，不显示断裂的存储 URL

### Requirement: 图片展示遵循同一授权
系统 MUST 通过受保护的 parse/evidence 入口获取图片，禁止客户端任意 path，并设置私有缓存与 MIME 安全响应。

#### Scenario: 有效已发布 Figure
- **WHEN** 用户请求同 parse 的合法 Figure Evidence
- **THEN** B resolver 返回受控 image 内容，响应 private/no-store、nosniff

#### Scenario: 路径或权限攻击
- **WHEN** 客户端传入任意文件路径、未发布 parse 或假 evidence
- **THEN** 拒绝且不读取任意对象，不暴露存储凭据

### Requirement: 会话交互遵循状态机
系统 MUST 将 D 的 owner/幂等/pending/busy/failed/stale_parse 状态清楚呈现，不流式显示未校验答案。

#### Scenario: 重复发送
- **WHEN** 用户双击发送同一问题
- **THEN** 相同 request_id 对应一个 turn，界面不重复展示答案

#### Scenario: parse 已更新
- **WHEN** 用户打开旧会话试图继续
- **THEN** 显示只读及新会话入口，不静默重绑定

#### Scenario: 模型不可用
- **WHEN** 模型请求失败或租约超时
- **THEN** 显示安全错误及显式重试，旧消息和原 PDF 保留

### Requirement: 生成动作与内容渲染安全
系统 MUST 用 POST/CSRF 执行生成并转义原文和模型输出，拒绝 raw HTML、脚本与远程媒体注入。

#### Scenario: 恶意模型或表格内容
- **WHEN** 文本含 script、事件 handler、恶意 Markdown 链接
- **THEN** 作为安全文本或受限内容显示，不执行脚本或加载外部媒体

#### Scenario: GET 或无 CSRF 生成
- **WHEN** 请求试图绕过 POST/CSRF
- **THEN** 不启动付费模型调用

### Requirement: 可访问性和 PDF 兼容
系统 MUST 保留原 PDF Range/下载行为、键盘可用 Evidence 及无 JavaScript 的基本阅读路径，不承诺原生 PDF bbox 高亮。

#### Scenario: 键盘与窄屏
- **WHEN** 用户用键盘导航且视口较窄
- **THEN** 四区和 source panel 可操作，焦点与状态可辨认

#### Scenario: 禁用脚本
- **WHEN** 浏览器不执行 JS
- **THEN** 仍可读已有分析、来源文字与 PDF 链接

#### Scenario: 原 PDF 分段读取
- **WHEN** 原查看器发送合法或非法 Range
- **THEN** 保持现有 206/416 行为与登录保护
