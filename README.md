<!-- auto-mas:i18n
{"display_name_i18n":{"zh_CN":"MFW 专项","en":"MFW Adapter","ja":"MFW アダプター"},"description_i18n":{"zh_CN":"运行任何带 interface.json 的 MaaFramework 项目","en":"Run any MaaFramework project that ships an interface.json","ja":"interface.json を備えた MaaFramework プロジェクトを実行します"},"tags_i18n":{"zh_CN":["脚本适配"],"en":["Script adapter"],"ja":["スクリプト"]}}
-->

# AUTO-MAS MaaFW Adapter

通用 MFW 专项插件：托管 `MaaFWConfig`，用宿主迁来的脚本级管理器跑通一轮，并提供外壳配置导入的 3 个端点（`/api/scripts/maafw/shell-instances`、`/import`、`/apply`）。

## 依赖

- `auto-mas-core`：插件 SDK。要带托管生命周期钩子、`ScriptTypeDecl.game_kind` / `desktop_session` 和 `teardown_blockers` 的宿主；SDK 的发行号带不带这些出口都一样，所以在导入时检查，没有就拒绝加载。
- `auto-mas-maafw-interface`、`auto-mas-maafw-native`：两块库。
- `auto-mas-maafw-adapter-kit`：专项共用库（属主入口、密码字段加解密、默认任务队列、保存前整理、备份归档；账号日志与通知文案、运行设置解析、代理次数、信号聚合、项目遥测、良性跳过的几句话）。
- `auto-mas-maafw-agent-env`、`auto-mas-maafw-runner`、`auto-mas-maafw-project-update`：三块服务插件。插件声明 `requires` 这三块的服务，还直接 import 它们的模块，所以依赖都写到次版本上限 `<0.3`。

宿主必须是不再内置 MFW / M9A / MSS 的让位分支；仍内置时加载会报 `ImportError`。

## 做法

- 执行：`expander.MaaFWExpander` 只是外壳，整轮交给 `manager.MaaFWEmbeddedManager`。L2 已经持有托管 X 锁，管理器以「宿主已持锁」模式运行，`_check` 里不再自己拿锁。管理器记的「跳过」交给 L3 收尾保留，托管级检查没过时 L3 记「异常」。
- 托管生命周期钩子（`plugin.Plugin`，实现在 `lifecycle` 和共用库里）：
  - `prepare_user_update`：保存账号前全局选项双写到各任务，再加密任务快照里按 interface 认出的密码字段；
  - `prepare_user_read`、`on_user_added`：任务队列为空的账号按项目默认写成实打实的队列（项目还没导入时留到以后）；
  - `on_script_cloned`：关掉开发者模式，从来源的载荷物化新托管的项目副本，副本记本插件为属主；
  - `on_script_removed`：删掉这个托管的项目副本（副本记着别的属主时不删），再起一次运行池对账。
- 声明函数：`game_kind` 按所选控制器收窄游戏类型（Adb 是模拟器，其余是客户端，判断不了返回 `None`）；`desktop_session` 在这次运行会选出的控制器是 Win32 时为真。
- 停用前：有托管还没收尾时 `teardown_blockers` 给出原因，宿主拒绝停用、重载、卸载。
- 跨插件调用：真正走服务的只有属主登记（`maafw.project.v1` 的 `owner.register` / `owner.unregister`，本插件提供 `maafw.owner.maafw_adapter.v1`）。其余直接 import 三块服务插件的模块，全部写在函数体内，或者放在只会在函数体内首次导入的模块（`manager`、`account_run`、`shell_api`、`shell_instances`）里。建计划、打码值、视图目录和上面那些文案、运行设置不经服务插件，直接从两块库和共用库取。
- 宿主能力经 `auto_mas_core.host` 的出口取；还没有出口的只剩通知任务基类 `app.core.notify.lifecycle.NotificationTaskBase` 和通知格式 `app.core.notify.formats.maafw`，只在宿主进程里跑。

## 开发与测试

本地联调时把本仓库以目录联接放到联调宿主的 `plugins/maafw_adapter`。单元测试不随仓库提交。
