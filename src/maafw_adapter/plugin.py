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

"""注册通用 MFW 的托管、账号、执行外壳、属主服务和外壳配置导入端点。

托管生命周期钩子（保存前、读取前、新建账号、复制托管、删除托管）接宿主原来给内置 MFW 的
配置回调；声明里的 ``game_kind`` / ``desktop_session`` 按托管当前配置判定游戏类型和桌面分身。

规则 L：本模块和它在模块顶层的整条导入链里，不出现别的插件包（三块服务插件、M9A、MSS）
的模块；跨插件的 import 一律写在函数体内。专项共用库 ``maafw_adapter_kit`` 不是插件。
"""

from typing import Any

from auto_mas_core import Config, ScriptAdapterPlugin, ScriptTypeDecl, TaskMode
from auto_mas_core.host.utils import get_logger

from . import expander as _expander
from . import lifecycle
from .api import router
from .config import MaaFWConfig, MaaFWUserConfig
from .expander import MaaFWExpander, prefetch_check

# 同一个开发版 SDK 号码同时出现在让位前后的宿主。仍内置 MFW 的宿主上不加载。
_builtin = Config.ScriptConfig.entry_types.get("MaaFWConfig")
if _builtin is not None and _builtin.__module__.startswith("app."):
    raise ImportError("当前 AUTO-MAS 仍内置 MFW / M9A / MSS，请换到让位分支")

# SDK 发行号带不带这几个出口都是 5.9.0b1，依赖下限区分不开，只能在这里查。没有钩子的宿主上
# 加载会让账号快照里的密码明文落盘、新账号没有默认队列，所以直接拒载。
if not (
    hasattr(ScriptAdapterPlugin, "on_script_cloned")
    and hasattr(ScriptAdapterPlugin, "teardown_blockers")
    and "game_kind" in ScriptTypeDecl.__dataclass_fields__
    and "desktop_session" in ScriptTypeDecl.__dataclass_fields__
):
    raise ImportError(
        "当前 AUTO-MAS 的插件 SDK 没有托管生命周期钩子，请先升级 AUTO-MAS"
    )

logger = get_logger("MFW 专项插件")

OWNER_NAME = "maafw_adapter"
OWNER_SERVICE = "maafw.owner.maafw_adapter.v1"
PROJECT_SERVICE = "maafw.project.v1"


class Plugin(ScriptAdapterPlugin):
    script_type_key = "MaaFW"
    requires = ("maafw.agent_env.v1", "maafw.runner.v1", PROJECT_SERVICE)
    provides_services = {OWNER_SERVICE: "owner_entry"}
    api_router = router
    decl = ScriptTypeDecl(
        script_type=MaaFWConfig,
        user_type=MaaFWUserConfig,
        expander_class=MaaFWExpander,
        plan_type=None,
        supported_modes=(TaskMode.AUTO_PROXY,),
        prefetch_check=prefetch_check,
        game_kinds=("emulator", "client"),
        supports_mod_avd=True,
        activity_game=None,
        game_kind=lifecycle.expected_game_kind,
        desktop_session=lifecycle.supports_desktop_session,
    )

    _owner = None

    async def pre_enable(self):
        refs = {
            "PlanConfig": Config.PlanConfig,
            "games": Config.GameConfig,
            "ScriptConfig": Config.ScriptConfig,
        }
        MaaFWConfig.related_config = refs
        MaaFWUserConfig.related_config = refs

    async def on_enable(self):
        from maafw_adapter_kit.owner_entry import BuiltinConfigOwner

        self._owner = BuiltinConfigOwner(OWNER_NAME, lambda: MaaFWConfig)
        await self.services.require(PROJECT_SERVICE)(
            "owner.register", name=OWNER_NAME, service=OWNER_SERVICE
        )

    async def on_disable(self):
        service = self.services.get(PROJECT_SERVICE)
        if service is not None:
            try:
                await service("owner.unregister", name=OWNER_NAME)
            except Exception as exc:  # noqa: BLE001 - 停用不因注销失败中断
                logger.warning(f"MFW 专项注销属主失败：{exc}")
        self._owner = None

    def owner_entry(self):
        """属主服务：返回本插件的属主入口对象（项目更新每次现取）。"""
        return self._owner

    async def teardown_blockers(self) -> list[str]:
        """有托管还在跑（管理器还没收尾）时拒绝停用、重载、卸载。"""
        running = _expander.active_run_count()
        return [f"有 {running} 个 MFW 托管正在运行"] if running else []

    # ── 托管生命周期钩子（宿主经本插件的调用门调用） ──

    async def prepare_user_update(
        self, script: Any, user: Any, data: dict[str, Any]
    ) -> None:
        """保存账号前：全局选项双写到各任务，再加密任务快照里按 interface 认出的密码。"""
        from maafw_adapter_kit.user_update import prepare_user_update

        await prepare_user_update(script, user, data=data)
        return None

    async def prepare_user_read(self, script: Any, user_ids: list[str] | None) -> None:
        """读账号前：任务队列为空的账号按项目默认（预设或默认勾选）补成实打实的队列。"""
        from maafw_adapter_kit.default_snapshot import prepare_user_read

        await prepare_user_read(script, user_ids=user_ids)

    async def on_user_added(self, script: Any, user: Any) -> None:
        """新账号：同读取前，项目已导入时当场写进默认队列，没导入时留到读取、运行前再补。"""
        from maafw_adapter_kit.default_snapshot import prepare_user_read

        await prepare_user_read(script, user_ids=[str(user.uid)])

    async def on_script_cloned(self, source: Any, target: Any) -> None:
        """复制托管：关掉开发者模式，新托管带上来源的项目副本（视图记本插件为属主）。"""
        await lifecycle.clone_script(source, target, owner=OWNER_NAME)

    async def on_script_removed(self, script_id: str) -> None:
        """删除托管：当场删掉它的项目副本，再起一次运行池对账。"""
        await lifecycle.remove_script(script_id, owner=OWNER_NAME)
