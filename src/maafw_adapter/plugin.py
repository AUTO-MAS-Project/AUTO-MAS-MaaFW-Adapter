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

规则 L：本模块和它在模块顶层的整条导入链里，不出现别的插件包（三块服务插件、M9A、MSS）
的模块；跨插件的 import 一律写在函数体内。
"""

from auto_mas_core import Config, ScriptAdapterPlugin, ScriptTypeDecl, TaskMode
from auto_mas_core.host.utils import get_logger

from .api import router
from .config import MaaFWConfig, MaaFWUserConfig
from .expander import MaaFWExpander, prefetch_check

# 同一个开发版 SDK 号码同时出现在让位前后的宿主。仍内置 MFW 的宿主上不加载。
_builtin = Config.ScriptConfig.entry_types.get("MaaFWConfig")
if _builtin is not None and _builtin.__module__.startswith("app."):
    raise ImportError("当前 AUTO-MAS 仍内置 MFW / M9A / MSS，请换到让位分支")

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
        # 规则 L：项目更新插件的属主入口类只在函数体内导入（越界 S3）
        from maafw_project_update.glue.owner_entry import BuiltinConfigOwner

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
