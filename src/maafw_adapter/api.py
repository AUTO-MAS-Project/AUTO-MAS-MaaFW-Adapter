#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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
"""外壳配置导入的 3 个端点与端点专用模型（从宿主 ``app/task/MaaFW/api.py`` 原样搬来）。

端点函数名、路径、docstring、``response_model`` 不改：operation id 由函数名和路径生成，
MCP 白名单靠它。端点实现 ``shell_api`` 只在端点函数体内导入。
"""

from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from auto_mas_core.host.models_schema import (
    MaaFWShellInstanceImportItem,
    MaaFWShellInstanceItem,
    OutBase,
)
from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)


class MaaFWShellInstancesIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 托管 ID")
    path: Optional[str] = Field(
        default=None,
        description="只扫这个目录（键位弹窗「选择其他目录」用，不写回脚本配置）；不传时先扫来源目录再扫内嵌副本",
    )


class MaaFWShellInstancesOut(OutBase):
    data: List[MaaFWShellInstanceItem] = Field(
        default_factory=list, description="项目目录里找到的外壳配置实例"
    )


class MaaFWShellInstanceImportIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 托管 ID")
    instanceIds: List[str] = Field(
        ..., min_length=1, description="要导入的实例 ID，每个建一个账号"
    )


class MaaFWShellInstanceApplyIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MFW 托管 ID")
    userId: str = Field(..., min_length=1, description="要覆盖任务队列的账号 ID")
    instanceId: str = Field(..., min_length=1, description="从哪份外壳实例导入")
    path: Optional[str] = Field(
        default=None,
        description="实例从哪个目录列出来的就传哪个（弹窗「选择其他目录」选的）；不传时先来源目录再内嵌副本，与列表同一口径",
    )


class MaaFWShellInstanceImportOut(OutBase):
    data: List[MaaFWShellInstanceImportItem] = Field(
        default_factory=list, description="逐个实例的导入结果，顺序同请求"
    )


class MaaFWShellInstanceApplyData(BaseModel):
    """覆盖到已有账号的结果：除了逐项成败与跳过项，还带实际写进账号配置的任务快照。

    界面直接拿它刷新本地状态，不用再回头拉一次账号配置——那样会把用户还没保存的其它改动
    一起冲掉。快照与 ``info`` 都是写入漏斗处理之后的样子（特调整理、密码加密），与读账号配置
    拿到的一致。
    """

    result: Optional[MaaFWShellInstanceImportItem] = Field(
        default=None,
        description="这次覆盖的结果；失败原因在 result.error 里，连结果是空的（找不到账号 / 实例）时为 null",
    )
    snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="实际写进账号配置的任务快照；失败时为空",
    )
    info: Dict[str, Any] = Field(
        default_factory=dict,
        description="写入时特调一并改掉的账号信息字段（如 M9A 把切换账号收进 Account）；没有为空",
    )


class MaaFWShellInstanceApplyOut(OutBase):
    data: MaaFWShellInstanceApplyData = Field(
        default_factory=MaaFWShellInstanceApplyData,
        description="覆盖结果与任务快照",
    )


# 端点按宿主原来的样子挂在 ``/api/scripts`` 下、带同样的标签：宿主是把这组路由
# include 进 ``APIRouter(prefix="/api/scripts", tags=["脚本管理"])`` 的。
_routes = APIRouter()


@_routes.post(
    "/maafw/shell-instances",
    tags=["MaaFW"],
    summary="列出项目目录里外壳（MFAAvalonia / MXU / MFW-PyQt6）保存的配置实例",
    response_model=MaaFWShellInstancesOut,
    status_code=200,
    openapi_extra={"x-auto-mas-mcp": True},
)
async def list_maafw_shell_instances(
    payload: MaaFWShellInstancesIn = Body(...),
) -> MaaFWShellInstancesOut:
    """新建托管引导最后一步用：外壳里配好的每份实例都可以导入成一个账号。只读外壳文件。"""

    from . import shell_api as maafw_shell_instances_api

    reply = await maafw_shell_instances_api.list_shell_instances(
        payload.scriptId, payload.path
    )
    return MaaFWShellInstancesOut(**reply.out_fields())


@_routes.post(
    "/maafw/shell-instances/import",
    tags=["MaaFW"],
    summary="把选中的外壳配置实例导入成用户",
    response_model=MaaFWShellInstanceImportOut,
    status_code=200,
    openapi_extra={"x-auto-mas-mcp": True},
)
async def import_maafw_shell_instances(
    payload: MaaFWShellInstanceImportIn = Body(...),
) -> MaaFWShellInstanceImportOut:
    """每个实例建一个账号：账号名称取实例名，任务队列与任务选项一起导入。

    逐个实例独立处理，失败原因与当前项目里对不上而跳过的任务 / 选项写在各项结果里。
    """

    from . import shell_api as maafw_shell_instances_api

    reply = await maafw_shell_instances_api.import_shell_instances(
        payload.scriptId, payload.instanceIds
    )
    return MaaFWShellInstanceImportOut(**reply.out_fields())


@_routes.post(
    "/maafw/shell-instances/apply",
    tags=["MaaFW"],
    summary="把一份外壳配置的任务队列覆盖到已有账号",
    response_model=MaaFWShellInstanceApplyOut,
    status_code=200,
)
async def apply_maafw_shell_instance(
    payload: MaaFWShellInstanceApplyIn = Body(...),
) -> MaaFWShellInstanceApplyOut:
    """脚本已经建好之后又在外壳里调过队列时，把那份队列与选项再同步到某个账号。

    与「导入成用户」共用同一套换算，所以当前项目里对不上的任务 / 选项同样会被跳过并列在结果里。
    覆盖的是任务队列与任务选项，账号名称不动。
    """

    from . import shell_api as maafw_shell_instances_api

    reply = await maafw_shell_instances_api.apply_shell_instance_to_user(
        payload.scriptId, payload.userId, payload.instanceId, payload.path
    )
    return MaaFWShellInstanceApplyOut(**reply.out_fields())


router = APIRouter()
router.include_router(_routes, prefix="/api/scripts", tags=["脚本管理"])

__all__ = ["router"]
