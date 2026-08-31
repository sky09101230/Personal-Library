## Purpose

为已登录用户提供面向整个科研工作区的首页导航，使用户不必先理解顶部菜单结构即可进入现有主要功能，并避免首页只呈现文献业务。

## ADDED Requirements

### Requirement: 首页展示主要功能入口
系统 SHALL 在首页展示文献库、文献上传、我的上传和共享 Skills 的可点击入口，每个入口 SHALL 指向对应的现有页面。

#### Scenario: 普通用户打开首页
- **WHEN** 已登录的普通用户访问首页
- **THEN** 页面显示文献库、文献上传、我的上传和共享 Skills 入口

### Requirement: 管理入口遵循权限
系统 MUST 只向 staff 用户展示首页管理后台入口。

#### Scenario: 普通用户不看到管理入口
- **WHEN** 非 staff 用户访问首页
- **THEN** 功能区不显示管理后台入口

#### Scenario: 管理员看到管理入口
- **WHEN** staff 用户访问首页
- **THEN** 功能区显示管理后台入口并指向管理后台
