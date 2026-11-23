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

"""外壳配置导入端点的结果载体（原样搬自项目更新 ``api.common.MaaFWApiReply``，MFW 服务化）。

只有通用 MFW 的外壳配置导入端点用它；端点只做 ``XxxOut(**reply.out_fields())``，字段与原来一字不差。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MaaFWApiReply:
    """专项函数交回端点的结果，端点只做 ``XxxOut(**reply.out_fields())``。

    ``code != 200`` 即失败，一律 ``status="error"``；``message`` / ``data`` 为 None 时
    不传，让响应模型用自己的缺省值——与业务还写在端点里时直接构造响应的写法逐字段一致。
    """

    code: int = 200
    message: str | None = None
    data: Any = None
    # 后台手动更新的身份标识；其它 MaaFW 端点不设置，不会出现在响应里。
    job_id: str | None = None

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> MaaFWApiReply:
        return cls(code=code, message=message, data=data)

    def out_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.code != 200:
            fields["code"] = self.code
            fields["status"] = "error"
        if self.message is not None:
            fields["message"] = self.message
        if self.data is not None:
            fields["data"] = self.data
        if self.job_id is not None:
            fields["jobId"] = self.job_id
        return fields


__all__ = ["MaaFWApiReply"]
