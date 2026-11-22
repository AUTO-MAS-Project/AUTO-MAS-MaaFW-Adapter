<!-- auto-mas:i18n
{"display_name_i18n":{"zh_CN":"MFW 专项","en":"MFW Adapter","ja":"MFW アダプター"},"description_i18n":{"zh_CN":"运行任何带 interface.json 的 MaaFramework 项目","en":"Run any MaaFramework project that ships an interface.json","ja":"interface.json を備えた MaaFramework プロジェクトを実行します"},"tags_i18n":{"zh_CN":["脚本适配"],"en":["Script adapter"],"ja":["スクリプト"]}}
-->

# AUTO-MAS MaaFW Adapter

通用 MFW 专项插件：托管 `MaaFWConfig`，用宿主迁来的脚本级管理器跑通一轮，并提供外壳配置导入的 3 个端点（`/api/scripts/maafw/shell-instances`、`/import`、`/apply`）。

## 依赖

- `auto-mas-core`：插件 SDK。
- `auto-mas-maafw-interface`、`auto-mas-maafw-native`：两块库。
- `auto-mas-maafw-agent-env`、`auto-mas-maafw-runner`、`auto-mas-maafw-project-update`：三块服务插件。插件声明 `requires` 这三块的服务，0.1.0 还直接 import 它们的模块，所以依赖都写到次版本上限 `<0.2`。

宿主必须是不再内置 MFW / M9A / MSS 的让位分支；仍内置时加载会报 `ImportError`。

## 0.1.0 的做法

- 执行：`expander.MaaFWExpander` 只是外壳，整轮交给 `manager.MaaFWEmbeddedManager`。L2 已经持有托管 X 锁，管理器以「宿主已持锁」模式运行，`_check` 里不再自己拿锁。
- 跨插件调用：真正走服务的只有属主登记（`maafw.project.v1` 的 `owner.register` / `owner.unregister`，本插件提供 `maafw.owner.maafw_adapter.v1`）。其余直接 import 三块服务插件的模块，全部写在函数体内，或者放在只会在函数体内首次导入的模块（`manager`、`account_run`、`shell_api`、`shell_instances`）里。
- 流程模块仍直接导入宿主的 `app.*`（`app.models.schema` 的 MaaFW 模型、通知格式等），只在宿主进程里跑。

## 开发与测试

本地联调时把本仓库以目录联接放到联调宿主的 `plugins/maafw_adapter`。单元测试不随仓库提交。
