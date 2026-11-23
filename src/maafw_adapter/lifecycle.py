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

"""托管生命周期钩子与声明函数的实现（插件类 ``plugin.Plugin`` 转调这里）。

照宿主原来内置 MFW 的配置回调（``seams/config_handler``、``script_lifecycle``）搬来：

- 复制托管：关掉开发者模式，从来源的载荷物化新托管的视图，新视图记本插件为属主；
- 删除托管：删掉这个托管的视图（视图记着别的属主时不删），再起一次运行池对账；
- 游戏类型：按所选控制器收窄，Adb 是模拟器，其余是客户端；
- 桌面分身：选出来的控制器是 Win32 才支持。

复制、删除托管经项目服务（``script_cloned_*``、``script_removed_*``），不导入别的插件（规则 L）。
"""

from __future__ import annotations

from typing import Any

from auto_mas_core.host.utils import get_logger
from maafw_adapter_kit.owner_entry import record_payload
from maafw_adapter_kit.services import (
    PROJECT_SCRIPT_CLONED,
    PROJECT_SCRIPT_REMOVED,
    script_cloned_request,
    script_removed_request,
)

from .services import client

logger = get_logger("MFW 专项插件")


async def clone_script(source: Any, target: Any, *, owner: str) -> None:
    """复制时物化源载荷；失败留待运行前重建，不影响已提交的托管复制。

    开发者模式不随复制继承，目标挂源原渠道组的 latest。组里没有正式载荷，或源是源码形态时
    先不建视图，第一次运行按来源目录导入。
    """

    # 目标托管的 FollowSource=False 是专项自己的配置，调用前自己写；物化视图、预约目标视图都在项目
    # 服务的 script_cloned 作业里做（原来直接调项目更新的 clone_embedded_copy）
    await target.update(
        type(target).model_validate({"Embedded": {"FollowSource": False}}),
        check_visibility=False,
    )
    source_record = record_payload(str(source.uid), source)
    reply = await client("复制托管").run(
        PROJECT_SCRIPT_CLONED,
        script_cloned_request(
            source_id=str(source.uid),
            target_id=str(target.uid),
            owner=owner,
            source_record=source_record,
        ),
    )
    if reply.skipped:
        if reply.reason == "follow_source_clone_unavailable":
            logger.info(
                f"复制托管时先不建视图，第一次运行前按来源目录导入: {reply.message}"
            )
        # occupied：目标视图正被占着，同原来拿不到预约时直接返回
    elif reply.failed:
        # 失败下次运行会按来源 / 载荷重建
        logger.warning(f"复制托管时建视图失败，将按需重建: {reply.message}")


async def remove_script(script_id: str, *, owner: str) -> None:
    """删掉这个托管的视图（不在 ``data/<uid>`` 下，宿主不管），再在后台起一次运行池对账。

    视图上记着别的属主时不删、记一句（那份视图不归本插件）。
    """

    # 看属主、删视图、起对账都在项目服务的 script_removed 作业里做（视图归项目更新管，它是唯一写入方）
    reply = await client("删除托管").run(
        PROJECT_SCRIPT_REMOVED, script_removed_request(script_id=script_id, owner=owner)
    )
    if reply.failed:
        # 原来删目录出错时异常往上抛（钩子失败），文案取原话
        raise RuntimeError(reply.message)
    if reply.get("outcome") == "kept_other_owner":
        logger.warning(
            f"删除托管 {script_id} 时视图记着属主 {reply.get('recorded_owner')}"
            f"（不是 {owner}），不删: {reply.get('view_path')}"
        )


def _project_interface(script: Any) -> Any | None:
    """读这个托管的视图里的 interface；视图还没建、读不出来时返回 ``None``。"""

    from maafw_interface.interface.loader import load_interface_model_cached
    from maafw_native.layout import view_dir

    root = view_dir(str(script.uid))
    if not root.is_dir():
        return None
    try:
        return load_interface_model_cached(root)
    except (OSError, ValueError):
        return None


def expected_game_kind(script: Any, patch: dict[str, Any]) -> str | None:
    """显式选择的控制器决定目标类别；没选、项目没导入或读不出 interface 时返回 ``None``。

    ``patch`` 是本次保存的补丁（运行时选目标只含 ``game``），里面改了控制器就按新值判。
    """

    info = patch.get("Info") if isinstance(patch, dict) else None
    controller = (info if isinstance(info, dict) else {}).get(
        "Controller", script.Info.Controller
    )
    if not controller:
        return None
    interface = _project_interface(script)
    if interface is None:
        return None
    selected = next(
        (item for item in interface.controller if item.name == controller), None
    )
    if selected is None:
        return None
    return "emulator" if selected.type == "Adb" else "client"


def supports_desktop_session(script: Any) -> bool:
    """按这次运行会选出的控制器判断：Win32 才能在桌面分身里跑；读不出来按不支持。"""

    from auto_mas_core.host.task_game import game_is_emulator
    from maafw_interface.runner.run_plan import (
        _select_controller,
        resolve_run_selection,
    )

    interface = _project_interface(script)
    if interface is None:
        return False
    try:
        name, _ = resolve_run_selection(
            interface,
            configured_controller=str(script.Info.Controller),
            emulator_selected=game_is_emulator(script),
            configured_resource=str(script.Info.Resource),
        )
        return _select_controller(interface, name).type == "Win32"
    except (OSError, ValueError):
        return False


__all__ = [
    "clone_script",
    "expected_game_kind",
    "remove_script",
    "supports_desktop_session",
]
