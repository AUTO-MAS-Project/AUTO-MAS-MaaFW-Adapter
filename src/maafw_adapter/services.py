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

"""通用 MFW 调三块服务插件（运行、agent 环境、项目 / 项目更新）的入口。

:data:`SLOT` 是本包模块级的服务槽：插件 ``on_enable`` 绑宿主给的解析器、``on_disable`` 解；管理器、
账号流程、外壳手里没有插件实例，经 :func:`client` 从槽里现取服务。:data:`REQUIRES` 是插件的
``requires``（共用库的操作名常量拼成，MFW 服务化实施方案附录 D：三个专项共有的 70 个加外壳导入的 4 个）。

本模块只导入专项共用库，不导入三块服务插件（规则 L）。
"""

from maafw_adapter_kit.services import (
    ADAPTER_REQUIRES,
    SHELL_IMPORT_OPS,
    ServiceClient,
    ServiceSlot,
)

PLUGIN_ID = "maafw_adapter"

#: 本插件的服务槽（插件启用时绑、停用时解）。
SLOT = ServiceSlot(PLUGIN_ID)

#: 插件 ``requires``：三个专项共有的 70 个操作名，加通用 MFW 外壳导入要的 4 个。
REQUIRES = (*ADAPTER_REQUIRES, *SHELL_IMPORT_OPS)


def client(caller: str = "") -> ServiceClient:
    """经 :data:`SLOT` 调服务的客户端（每次调用都现取服务）；``caller`` 只进后端 debug 日志。"""

    return ServiceClient(SLOT, caller=caller)


__all__ = ["PLUGIN_ID", "REQUIRES", "SLOT", "client"]
