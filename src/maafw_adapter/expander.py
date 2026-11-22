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

"""通用 MFW 的 L3 外壳：整轮交给沿用的脚本级管理器。

插件路径在建 L3 之前，L2 已经拿了托管 X 锁（不可重入），所以管理器以「宿主已持锁」
模式运行。旧路径由 L2 交给管理器的几样（history、context、``_manager_controls_users``）
在这里补上。管理器模块经运行积木 import ``maa``，只在函数体内导入（规则 L）。
"""

from __future__ import annotations

from typing import Any

from auto_mas_core import TaskMode, UserExpander

# 还没收尾的外壳（插件停用前的 teardown_blockers 看它）
_ACTIVE_RUNS: set[MaaFWExpander] = set()


def active_run_count() -> int:
    """正在跑（管理器还没收尾）的 MFW 托管数。"""

    return len(_ACTIVE_RUNS)


class MaaFWExpander(UserExpander):
    """整轮交给沿用的脚本级管理器；L3 只做外壳。"""

    async def main_task(self) -> None:
        await self.script_info.set_state(status="运行")
        self._entered = True
        from .manager import _BENIGN_SKIPS, MaaFWEmbeddedManager  # 规则 L：函数内导入

        manager = MaaFWEmbeddedManager(
            self.script_info, host_locked_config=self.script_config
        )
        manager.history = self.history
        manager.context = self.context
        manager.maintenance = False
        # L2 收尾时复位（app/task/script_expander.py）
        self.script_info._manager_controls_users = True
        _ACTIVE_RUNS.add(self)
        try:
            await manager._execute_task()
            error = manager.execution.error
            if (
                error is not None
                and type(error).__name__ == "FluxdownCancelUnconfirmed"
            ):
                raise error
            # 管理器记了「跳过」（项目正在更新 / 被占用，或账号全因停服维护跳过）时告诉 L3，
            # 免得 L3 收尾把它改成「完成」；托管级检查没过（管理器记「异常」、已发过错误提示）
            # 按 SDK 对 check() 返回原因的口径抛出，L3 收尾记「异常」
            if manager.check_result in _BENIGN_SKIPS:
                self._skipped = manager.check_result
            elif manager.check_result not in ("Pass", "-"):
                raise ValueError(manager.check_result)
            elif self.script_info.info.status == "跳过":
                self._skipped = "跳过"
        finally:
            _ACTIVE_RUNS.discard(self)
            await manager.callbacks.close()
            if self.task_info.mode == TaskMode.AUTO_PROXY:
                manager.finalize_completion_details(self.script_info)

    def build_worker(self, user: Any, config: Any) -> Any:
        raise NotImplementedError("0.1.0 由 main_task 整轮交给管理器")


async def prefetch_check(config: Any) -> list:
    """队列预下载：按项目更新模式和凭据发现发行包更新（沿用管理器的同名静态方法）。"""

    from .manager import MaaFWEmbeddedManager  # 规则 L：函数内导入

    return await MaaFWEmbeddedManager.check_prefetch(config)


__all__ = ["MaaFWExpander", "prefetch_check"]
