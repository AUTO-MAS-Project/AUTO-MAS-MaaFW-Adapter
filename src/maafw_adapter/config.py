#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""通用 MFW 托管与账号配置。

字段从宿主 ``app/models/config/script.py`` 的 ``MaaFWUserConfig`` / ``MaaFWConfig`` 原样搬来，
默认值与 description 不变；基类换成 SDK 的 ``UserEntry`` / ``ScriptEntry``，账号集合
``UserData`` 改名 ``users``（旧文档在 ``normalize_payload`` 里改名）。类名不能改：
项目更新按 ``type(config).__name__`` 推出托管种类。

保存账号前的任务快照整理（全局选项双写、密码加密）在插件的 ``prepare_user_update`` 钩子里做
（``plugin.py``），宿主 ``Config.update_user`` 在写入前调它，这里不再覆盖 ``update()``。
"""

from __future__ import annotations

import json
import warnings
from copy import deepcopy
from datetime import datetime
from pathlib import Path as NativePath
from typing import Annotated, ClassVar, Literal

from auto_mas_core import (
    DeclarativeBlock,
    HostBlock,
    PluginBlock,
    ScriptEntry,
    UserEntry,
)
from auto_mas_core.host.config import (
    ConfigCollection,
    ConfigGroup,
    Virtual,
    collection,
    encrypted,
    legacy,
    tz,
    ui,
    virtual_field,
)
from auto_mas_core.host.config_types import (
    STANDARD_BLOCKED_DIRS,
    CliArgumentString,
    FilePath,
    JsonDictString,
    JsonListString,
    path_policy,
)
from auto_mas_core.host.models_config_queue import Webhook
from auto_mas_core.host.models_config_shared import (
    AccountNameFields,
    AccountRunFields,
    AccountRunStatusFields,
    AccountScriptHookFields,
    _tag_last_status,
    _tag_notes,
    _tag_proxy,
    _tag_remained_days,
    local_timezone,
    none_as,
)
from pydantic import Field

# 配置分组 ``Info`` / ``Notify`` 与 SDK 基类上同名的嵌套类重名（基类的字段是小写的 ``info``、
# ``notify``），pydantic 每次建类都报「shadows an attribute in parent」。分组名就是落盘和接口里的键，
# 不能改名，只把这两个类的这句警告关掉。
warnings.filterwarnings(
    "ignore",
    message=r'Field name "(Info|Notify)" in "MaaFW(User)?Config" shadows an attribute',
    category=UserWarning,
)


class MaaFWUserConfig(UserEntry):
    "MaaFW 账号配置"

    ui_blocks = (
        HostBlock("config_restore"),
        DeclarativeBlock(("Info",)),
        PluginBlock("user", fallback_groups=("Task", "Device")),
        DeclarativeBlock(("Notify",)),
        HostBlock("webhooks"),
    )

    class DataFields(AccountRunFields, AccountRunStatusFields):
        PeriodTaskRecords: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="MaaFW 周期任务完成记录，结构为 weekly/monthly -> task name -> period key",
        )

    Data: DataFields = Field(default_factory=DataFields)

    class DeviceFields(ConfigGroup):
        AdbAddress: str = Field(
            default_factory=lambda: "",
            description="当前账号覆盖 ADB 地址，留空时使用托管级模拟器配置",
        )

        HWnd: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 / Gamepad 窗口句柄，0 表示未指定",
        )

        PlayCoverAddress: str = Field(
            default_factory=lambda: "", description="PlayCover 地址"
        )

        PlayCoverUuid: str = Field(
            default_factory=lambda: "", description="PlayCover UUID"
        )

    Device: DeviceFields = Field(default_factory=DeviceFields)

    class InfoFields(AccountNameFields, AccountScriptHookFields):
        Id: Annotated[str, legacy(group="Info", name="Account"), encrypted()] = Field(
            default_factory=lambda: "",
            description="账号信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务",
        )

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="密码信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class TaskFields(ConfigGroup):
        SelectedPreset: str = Field(
            default_factory=lambda: "",
            description="当前选中的 interface preset 名称，留空时使用 interface 默认逻辑",
        )

        # 新队列的 keepUnchecked 标记随 JSON 原样保存；无标记的旧 false 实例仍隐藏。
        TaskSnapshot: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="当前账号的任务快照，结构为 taskOrder/taskChecked/taskOptions/globalOptions， 可选 taskLabels（用户给某一份实例起的显示名，只影响界面显示）， 可选 taskSchedules（``{实例 id: {weekdays: [1..7]}}``，ISO 星期 1=周一，升序去重；只在本机今天的星期在其中时运行这一份，开跑建计划时判一次；七天全选即不限制、不写这一项，空表或非法值按不限制处理）； 除 globalOptions 外各键都是任务实例 id，同一个任务可以重复入队（见 MaaFWTaskSnapshot）； globalOptions 是全局选项的值，每个账号一份、所有任务共用。 默认的空快照在创建账号、读取账号与运行前按项目默认（预设或默认勾选）补成实打实的队列， 见 app/task/MaaFW/tools/embedded/default_snapshot.py",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        """生成 MaaFW 账号标签列表"""
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {
                "text": f"上次：{_tag_last_status(last_status)}",
                "color": "red" if last_status == "失败" else "green",
            }
        )
        tags.append(_tag_proxy(self, "任务"))
        tags.append(_tag_remained_days(self))
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)

    related_config: ClassVar = {}

    class Metadata(UserEntry.Info):
        name: Virtual[str] = None  # pyright: ignore[reportIncompatibleVariableOverride]
        enabled: Virtual[bool] = None  # pyright: ignore[reportIncompatibleVariableOverride]

    info: Metadata = Field(default_factory=Metadata)  # pyright: ignore[reportIncompatibleVariableOverride]

    @virtual_field("info.name")
    def plugin_name(self):
        """向宿主提供已有账号名称。"""
        return self.Info.Name

    @virtual_field("info.enabled")
    def plugin_enabled(self):
        """向宿主提供已有账号启用状态。"""
        return self.Info.Status


class MaaFWConfig(ScriptEntry):
    """MaaFW 项目配置。

    特调通过继承配置分组扩展默认值，并显式声明自身的账号集合类型。
    """

    related_config: ClassVar = {}
    DEFAULT_SCRIPT_NAME: ClassVar = "新 MFW 托管"
    USER_CONFIG_CLASS: ClassVar = MaaFWUserConfig
    DEFAULT_TASK_TIME_LIMIT_OVERRIDES: ClassVar = "{ }"
    ui_blocks = (
        PluginBlock("script", fallback_groups=("Info", "Embedded", "Device", "Game", "Run")),
        HostBlock("game_binding"),
        DeclarativeBlock(("Update",)),
    )

    class DeviceFields(ConfigGroup):
        AdbAddress: str = Field(
            default_factory=lambda: "",
            description="ADB 地址，留空时启动托管级模拟器获取",
        )

        AdbInputMethods: Annotated[int, Field(ge=-999, le=999999999999)] = Field(
            default_factory=lambda: -1,
            description="ADB 输入方法，默认优先模拟器增强，失败后回退到 MaaTouch / MiniTouch / ADB 同上，仅第二层适用；第一层运行期写死 InputMethods=18446744073709551607",
        )

        AdbPath: FilePath = Field(
            default_factory=lambda: None,
            description="ADB 路径，留空时从 MAS 模拟器配置或 MaaFW Toolkit 推导",
        )

        AdbScreencapMethods: Annotated[int, Field(ge=-999, le=999999999999)] = Field(
            default_factory=lambda: -57,
            description="ADB 截图方法，默认优先模拟器增强，失败后回退到 ADB 截图 仅第二层（MAS 进程内 runner）适用：第一层由外壳自己创建控制器，运行期按 M9A 专项的既验证取值写死（ScreencapMethods=64），本项不参与外部运行， 接线前不要暴露到前端，否则用户改了不会生效也没有提示",
        )

        GamepadType: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Gamepad 类型，默认 Xbox360",
        )

        HWnd: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 / Gamepad 窗口句柄，0 表示未指定",
        )

        PlayCoverAddress: str = Field(
            default_factory=lambda: "", description="PlayCover 地址"
        )

        PlayCoverUuid: str = Field(
            default_factory=lambda: "", description="PlayCover UUID"
        )

        Win32KeyboardMethod: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 键盘方法，0 表示使用 interface 声明或 MaaFW 默认值",
        )

        Win32MouseMethod: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 鼠标方法，0 表示使用 interface 声明或 MaaFW 默认值",
        )

        Win32ScreencapMethod: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 截图方法，0 表示使用 interface 声明或 MaaFW 默认值",
        )

    Device: DeviceFields = Field(default_factory=DeviceFields)

    class EmbeddedFields(ConfigGroup):
        FollowSource: bool = Field(
            default_factory=lambda: False,
            description="跟随来源目录（开发者模式），默认关。开着时每次运行前比一下来源目录（投影会带走的 文件的路径 + 大小 + 修改时间），变了就重新导入到这个托管自己的私有渠道（不比版本、 不与同项目其它托管共用版本），不做项目更新；关掉后回到 Update.Channel 的组。 见 tools/embedded/embedded_project.py「跟随来源目录」一节。",
        )

        ImportedAt: Annotated[
            datetime | None, tz(local_timezone), ui(widget="datetime", format="hms")
        ] = Field(default=None, description="导入时间，仅展示；空值表示尚未导入")

        Report: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="投影报告（省下多少、外壳家族、排除条数与原因），JSON 字符串",
        )

        SourceVersion: str = Field(
            default_factory=lambda: "",
            description="由 AUTO-MAS 内嵌一份按 interface 白名单投影的副本来运行。副本在 data/mfw/<托管 uuid 前 12 位>/，由托管 ID 推出、不进配置、用户不可手改； Info.Path 继续存用户选的来源目录。更新落地时同样只写白名单内的条目。 导入时来源的 interface 版本，仅展示",
        )

    Embedded: EmbeddedFields = Field(default_factory=EmbeddedFields)

    class GameFields(ConfigGroup):
        Arguments: CliArgumentString = Field(
            default_factory=lambda: "",
            description="游戏启动参数，仅 DirectExe 模式使用；URL 模式的参数写进链接",
        )

        CloseMode: Literal["Script", "OnFailure", "Always"] = Field(
            default_factory=lambda: "OnFailure",
            description="AttachOnly 模式下结束后谁关游戏：Script 交给脚本（MAS 不关）；OnFailure 本次运行没正常完成（失败、超时、停止、异常）时由 MAS 关；Always 结束后一律由 MAS 关。MAS 只关本次运行开始之后才出现的进程，重试之间不关。DirectExe 与 URL 模式忽略它",
        )

        Hotkeys: JsonDictString = Field(
            default_factory=lambda: "{}",
            description='托管级键位（PI v2.8 hotkey 选项）：``{option 名: {字段名: 组合键字符串}}``， 组合键写成「修饰键+…+主键」（如 ``"Ctrl+E"``）。只存与 interface 默认不同的 字段；运行时叠加到每个任务实际生效的 hotkey 选项上，盖过账号快照 / 预设里的值。 仅 Win32 控制器生效（Adb 等其他控制器不叠加）。interface 里已没有的 option / 字段静默忽略，映射不了的值告警后回落到快照 / 默认值（runner/run_plan.py）。',
        )

        LaunchMode: Literal["DirectExe", "URL", "AttachOnly"] = Field(
            default_factory=lambda: "DirectExe",
            description="游戏生命周期模式：DirectExe 由 MAS 按 exe 启动、结束后关闭；URL 由 MAS 打开链接拉起游戏、结束后关闭；AttachOnly 由脚本或用户自己启动，MAS 只接管窗口，结束后是否由 MAS 关闭见 CloseMode",
        )

        LaunchPath: FilePath = Field(
            default_factory=lambda: None,
            description="游戏 exe：DirectExe 模式下 MAS 启动它；URL 模式下必填，用来认出游戏（是否已在运行、等窗口、关闭、Unity 分辨率）；AttachOnly 模式下可选，用来认出要关闭的游戏",
        )

        LauncherPath: FilePath = Field(
            default_factory=lambda: None,
            description="AttachOnly 模式下可选的启动器 exe，MAS 兜底关闭游戏时一并关闭本次运行期间打开的启动器",
        )

        PackageName: str = Field(
            default_factory=lambda: "",
            description="安卓游戏包名，Adb controller 用：启动模拟器时顺带把游戏拉起来。 留空表示从项目的 pipeline 里自动识别（见 embedded/game_package.py）； 自动识别是启发式的，填了这里就以这里为准。识别不出且没填则不启动游戏。",
        )

        URL: str = Field(
            default_factory=lambda: "",
            description="URL 模式下 MAS 打开的链接，如 steam://rungameid/<appid>",
        )

        UnityResolution: Literal["Off", "1920x1080", "1280x720"] = Field(
            default_factory=lambda: "Off",
            description="DirectExe 与 URL 模式下，启动游戏前按 exe 路径反查 Unity 注册表，临时把分辨率改成所选 尺寸的窗口模式，游戏关闭后恢复原值（tools/embedded/game_resolution.py）。 只对 Unity 引擎的游戏有效；游戏已在运行时不改。Off 表示不碰。",
        )

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 120,
            description="游戏启动等待时间（秒）：既是等窗口出现的上限，也是窗口出现后等画面稳定的上限。 Unity 游戏窗口出现时还在黑屏加载，登录界面往往要二三十秒后才渲染出来； MaaEnd 的 SceneManager 见连续画面不变十几秒就判「环境识别异常」直接失败。 等画面时 worker 每秒截一帧，有内容且连续几秒不变就提前下发，等不到才等满； MaaFW 初始化（加载资源、连 controller、起 agent）与之重叠而不是干等。 只对本轮由 MAS 拉起的游戏生效，AttachOnly 与「游戏已在运行」不等画面。",
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Controller: str = Field(
            default_factory=lambda: "",
            description="MaaFW controller 名称，留空时按 interface 和设备配置自动选择",
        )

        Name: str = Field(
            default_factory=lambda: "新 MFW 托管", description="MaaFW 托管名称"
        )

        # 导入完成后来源可删除；完整保留版本号目录名，不能去后缀或清空。
        Path: Annotated[
            NativePath | None,
            path_policy(kind="folder", blocked_dirs=STANDARD_BLOCKED_DIRS),
        ] = Field(
            default_factory=lambda: None,
            description="MaaFW 项目的导入来源目录，应包含 interface.json；导入后可删，删了也原样保留",
        )

        ProjectLabel: str = Field(
            default_factory=lambda: "",
            description="项目标签，可用于区分同一 ProjectInterface 的不同实例",
        )

        Resource: str = Field(
            default_factory=lambda: "",
            description="MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        ExecutionSession: Literal["main", "desktop"] = Field(
            default="main", description="单独启动托管时使用的 Windows 会话"
        )

        DailyOnceTasks: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="每天正常完成一次后，当天剩余时间跳过的 MaaFW 任务名列表",
        )

        GameUpdateMode: Literal["Off", "Check", "AutoInstall"] = Field(
            default_factory=lambda: "Off",
            description="游戏客户端更新：Off 不检查 / Check 只检查，落后时本次判失败并提示手动更新 / AutoInstall 落后时自动下载安装包并 adb 安装（保留游戏数据）。只在特调实现了 游戏更新钩子（当前只有 M9A）且 controller 是 ADB 时生效，通用 MaaFW 不读。 Off 必须排第一：OptionsValidator 纠错回退的是 options[0]。",
        )

        LoopGuard: bool = Field(
            default_factory=lambda: True,
            description="原地打转检测（默认开）。任务在短周期里反复执行同一串节点（周期 ≤ 8 步、每轮都有点击 / 滑动等物理动作）、识别结果又几乎不变时判定卡死：≥ 200 轮且持续 ≥ 10 分钟就停掉这个任务，收尾与单任务超时同一口径（截图、第一个任务或关键任务 结束本轮，其余记失败后继续）。判据见 tools/core/runner/loop_guard.py。 默认值双轨：新建托管取类默认开；既有托管配置里写着这个键的（用户可能动过）原样保留，配置里没有这个键的（从没保存过，肯定没动过）落到类默认，同样是开。",
        )

        MonthlyOnceTasks: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="每月正常完成一次后，本月剩余时间跳过的 MaaFW 任务名列表",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0,
            description="运行引擎，决定「谁来跑」： 代理次数限制",
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单次运行时间限制（分钟），套在单个账号的整次运行上。截止时刻随 job 文件交给 worker：到点它自己停掉当前任务、截一张超时图、带回已完成的任务；宿主只在 worker 没能及时停下时才强杀（那时既没有截图也没有进度）。MaaFW 项目一轮日常 动辄几十分钟，30 分钟默认值实测常被误伤，放宽到 120。",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3,
            description="运行次数限制。重试不关游戏、不再等启动，从当前画面接着跑； 脚本自己的加载超时（MaaEnd 回大世界 20s）一次抖动就把整轮判失败， 只给一次机会时用户看到的就是「从来没成功过」，默认与其他专项一样 3 次。",
        )

        TaskTimeLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 45,
            description="单个任务的时限（分钟），0 表示不限。某个任务卡住时到点只停它、截一张超时图， 记一条任务失败后接着跑后面的任务（计划里第一个任务超时则结束本轮）；不再让 一个卡住的任务吃掉整轮 RunTimeLimit 的时间。 默认 45 而不是 30：M9A 智能均衡刷材料正常 1–22 分钟，自动深眠在新内容日 实测 33.7 分钟，30 会误伤正常运行。",
        )

        TaskTimeLimitOverrides: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="按任务名覆盖的单任务时限（分钟），键是 MaaFW 任务名；值 0 表示该任务不限。 默认值由类属性 DEFAULT_TASK_TIME_LIMIT_OVERRIDES 决定（特调可内置几条）； 只在配置里没有这个键时生效，用户存过的值（含清空成 {}）原样保留。",
        )

        WeeklyOnceTasks: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="每周正常完成一次后，本周剩余时间跳过的 MaaFW 任务名列表",
        )

    Run: RunFields = Field(default_factory=RunFields)

    class SelectionFields(ConfigGroup):
        Controller: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="当前阶段保留：manager.py 仍从 Selection.* 读取运行范围， 字段迁移到 Info.* / 账号任务配置属于后续 P3 前端回收。 选中的 controller 列表",
        )

        Resource: JsonListString = Field(
            default_factory=lambda: "[ ]", description="选中的 resource 列表"
        )

        Tasks: JsonListString = Field(
            default_factory=lambda: "[ ]", description="选中的 task 列表"
        )

    Selection: SelectionFields = Field(default_factory=SelectionFields)

    class TaskFields(ConfigGroup):
        Templates: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description='账号页任务队列的自定义模板，同一托管的账号共用。JSON 列表，每项 ``{"name": 模板名, "snapshot": {taskOrder, taskChecked, taskOptions, taskLabels?, taskSchedules?}}``， 快照形状同账号的 Task.TaskSnapshot（键是任务实例 id），但不含受管任务、密码字段 与全局选项（globalOptions 归各账号自己）； 名称在托管内唯一。运行流程不读它，只由账号页套用到某个账号的队列。',
        )

    Task: TaskFields = Field(default_factory=TaskFields)

    class UpdateFields(ConfigGroup):
        # 默认增量：GitHub 源按区间差量、Mirror 酱源要差量包，失败都回退全量。
        # 全量的好处只有一条——队列里可以提前预下载（增量依赖开跑时的当前载荷，
        # 不预下载，见 embedded_manager.prefetch_script_update）。
        PackageMode: Literal["full", "incremental"] = Field(
            default="incremental",
            description="更新方式：全量或优先增量；增量依赖完整且匹配的基线，必要时回退全量。",
        )
        AutoUpdateMode: Annotated[
            Literal["Off", "BeforeRun", "AfterRun"],
            legacy(
                group="Update",
                name="IfAutoUpdate",
                convert=lambda value: "Off" if value is False else "BeforeRun",
            ),
        ] = Field(
            default_factory=lambda: "BeforeRun",
            description="项目自动更新时机：Off 不更新，BeforeRun 在账号任务开始前更新。旧配置 AfterRun 兼容为运行前更新。更新和环境准备耗时不计入账号任务时限。",
        )

        Channel: Literal["stable", "beta"] = Field(
            default_factory=lambda: "stable",
            description="更新渠道只有稳定版与测试版，默认稳定版，要测试版由用户手动切。 不给「跟随全局」：全局那个 Update.Channel 是 MAS 自身的发布通道， 和脚本本体的版本档位是两回事，串在一起只会让人猜。 Mirror 酱还支持 channel=alpha，**故意不开放**——那是项目方的内部 验证档，稳定性无保证，而这里更新的是用户日常在跑的脚本本体。 这两个值必须与前端 updateChannelOptions 和 schema 的 Literal 一致： 三处任一多给一档，用户选了就会 422 或被静默纠回默认值。 旧配置里的空串现在是非法值，会被 correct() 回退成 options[0]， 即 stable——这里的顺序同样不能随意调换。",
        )

        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="Mirror 酱 CDK，由用户自己填。**不做全局兜底**：全局那个服务的是 AUTO-MAS 自身的更新，和脚本本体不是一回事，串在一起只会让人猜 自己在用哪个。选 Mirror 酱作为下载源时这一项必填。 （合并逻辑见 tools/embedded/update_credentials.py）",
        )
        ProxyAddress: str = Field(
            default_factory=lambda: "",
            description="托管级网络代理，给这个项目的更新包下载与运行环境安装（uv / pip、 binding 源码兜底）用。与 CDK / 渠道不同，这一项**留空就跟随全局** `Update.ProxyAddress`（设置 → 其他 → 网络代理），填了就只走自己的： 代理解决的是「这台机器连不连得上」，多数人全局一份就够，个别项目 的源在别的网络才需要单独指。格式同全局项，`host:port` 不带协议时 补 `http://`（合并逻辑见 tools/embedded/update_credentials.py）。",
        )

        Source: Literal["GitHub", "MirrorChyan"] = Field(
            default_factory=lambda: "GitHub",
            description="更新包的下载源，由用户显式选择——**不做自动分流**。 版本检查始终走 Mirror 酱（无 CDK 也能查），但下载去哪由这一项决定： 选 Mirror 酱就必须自己填 CDK，CDK 不可用时明确报错，不悄悄换成 GitHub——用户得知道自己在从哪下载，出问题才查得动。 默认 GitHub：零配置即可用，与全局 Update.Source 的默认值一致。 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**， 不是这里的默认值。旧配置里 Source 是空串（旧默认），加载时会被 correct 成第一项并写回磁盘——GitHub 必须排在前面，否则所有既有托管会被静默改成 Mirror 酱，而它们并没有 CDK，每次运行都更新失败。",
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)
    users: ConfigCollection[MaaFWUserConfig] = collection(MaaFWUserConfig)

    class Metadata(ScriptEntry.Info):
        name: Virtual[str] = None  # pyright: ignore[reportIncompatibleVariableOverride]

    info: Metadata = Field(default_factory=Metadata)  # pyright: ignore[reportIncompatibleVariableOverride]

    @virtual_field("info.name")
    def plugin_name(self):
        """向宿主提供已有托管名称。"""
        return self.Info.Name

    @classmethod
    def normalize_payload(cls, data):
        """迁移原账号集合名称，保留 UID、顺序及字段。"""
        data = deepcopy(data)
        if "UserData" in data:
            data["users"] = data.pop("UserData")
        if "UserData" in data.get("SubConfigsInfo", {}):
            data["SubConfigsInfo"]["users"] = data["SubConfigsInfo"].pop("UserData")
        return data

    async def _activate_from_payload(self, payload, *, regenerate_uuids=False):
        """在集合激活边界转换旧配置文档。"""
        await super()._activate_from_payload(
            type(self).normalize_payload(payload), regenerate_uuids=regenerate_uuids
        )


__all__ = ["MaaFWConfig", "MaaFWUserConfig"]
