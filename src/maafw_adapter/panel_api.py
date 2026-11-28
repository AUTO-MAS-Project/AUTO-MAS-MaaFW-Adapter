"""通用 MaaFW 编辑面板的作用域端点。"""

import asyncio
import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from auto_mas_core import Config, Plugin
from auto_mas_core.host.task_game import game_is_emulator
from fastapi import APIRouter, Depends, HTTPException, Request
from maafw_adapter_kit.option_secrets import is_sealed_secret
from maafw_adapter_kit.owner_entry import record_payload, write_or_raise
from maafw_adapter_kit.services import (
    PROJECT_CONFIRM,
    PROJECT_CONTEXT,
    PROJECT_UPDATE_DISCOVER,
    PROJECT_UPDATE_UPDATE,
    PROJECT_VIEW_ENSURE,
    ProjectOpener,
    Reply,
    confirm_request,
    open_request,
    project_context_request,
    project_job_request,
    update_request,
    view_ensure_request,
)
from maafw_interface.interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from maafw_interface.interface.models import map_password_values, password_input_names
from maafw_interface.interface.preview import build_interface_preview_data
from maafw_interface.runner.game_package import resolve_game_package, resource_paths_for
from pydantic import BaseModel, Field, JsonValue, StringConstraints, ValidationError

from .api import (
    MaaFWShellInstanceApplyIn,
    MaaFWShellInstanceImportIn,
    MaaFWShellInstancesIn,
    apply_maafw_shell_instance,
    import_maafw_shell_instances,
    list_maafw_shell_instances,
)
from .config import MaaFWConfig
from .services import PLUGIN_ID, client

router = APIRouter()


def _authorize(request: Request, entry, page: str) -> None:
    activation = request.headers.get("x-plugin-ui-activation", "")
    if (
        request.headers.get("x-plugin-ui-provider") != PLUGIN_ID
        or request.headers.get("x-plugin-ui-page") != page
    ):
        raise HTTPException(403, "面板与配置类型不匹配")
    mount = Plugin.frontend_block_pages(entry).get(page)
    if mount is None or mount.activationId != activation:
        raise HTTPException(409, "插件界面已失效，请重新打开")


def _script(script_id: UUID) -> MaaFWConfig:
    try:
        script = Config.ScriptConfig[script_id]
    except KeyError as exc:
        raise HTTPException(404, "找不到 MFW 托管") from exc
    if type(script) is not MaaFWConfig:
        raise HTTPException(404, "找不到通用 MFW 托管")
    return script


async def _script_panel(request: Request, script_id: UUID) -> MaaFWConfig:
    script = _script(script_id)
    _authorize(request, script, "script")
    return script


async def _user_panel(request: Request, script_id: UUID, user_id: UUID) -> MaaFWConfig:
    script = _script(script_id)
    try:
        user = script.users[user_id]
    except KeyError as exc:
        raise HTTPException(404, "找不到 MFW 账号") from exc
    _authorize(request, user, "user")
    return script


ScriptPanel = Annotated[MaaFWConfig, Depends(_script_panel)]
UserPanel = Annotated[MaaFWConfig, Depends(_user_panel)]


def _writable(script: MaaFWConfig) -> None:
    if script.is_locked:
        raise HTTPException(409, "托管正忙，稍后重试")


def _checked(reply: Reply) -> Reply:
    if reply.failed or reply.skipped:
        raise HTTPException(503 if reply.lost else 409, reply.message)
    return reply


async def _root(script: MaaFWConfig) -> Path:
    service = client("编辑面板项目视图")
    if script.is_locked:
        # 只读面板也可查看任务，但不在锁定时重建视图。
        record = record_payload(str(script.uid), script)
        reply = await service.call(PROJECT_CONTEXT, project_context_request(record))
        return Path(_checked(reply)["view_dir"])
    reply = await service.run(
        PROJECT_VIEW_ENSURE, view_ensure_request(str(script.uid), "")
    )
    return Path(_checked(reply)["root"])


def _read_preview(root: Path):
    return build_interface_preview_data(root, load_interface_model_cached(root))


async def _preview(script: MaaFWConfig):
    if script.Info.Path is None and script.Embedded.ImportedAt is None:
        return None
    root = await _root(script)
    try:
        return await asyncio.to_thread(_read_preview, root)
    except MaaFWInterfaceLoadError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/editor/script/{script_id}")
async def script_context(script: ScriptPanel):
    return {
        "path": script.Info.Path,
        "preferAdb": game_is_emulator(script),
        "preview": await _preview(script),
    }


@router.get("/editor/user/{script_id}/{user_id}")
async def user_context(script: UserPanel):
    return {
        "controller": script.Info.Controller,
        "resource": script.Info.Resource,
        "preferAdb": game_is_emulator(script),
        "templates": script.Task.Templates,
        "preview": await _preview(script),
    }


class ImportProjectIn(BaseModel):
    path: str = Field(min_length=1)


@router.post("/editor/script/{script_id}/project")
async def import_project(script: ScriptPanel, payload: ImportProjectIn):
    try:
        path = type(script.Info).model_validate({"Path": payload.path}).Path
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()[0]["msg"]) from exc
    if path is None or not await asyncio.to_thread(path.is_dir):
        raise HTTPException(422, "请选择有效的 MFW 项目目录")
    try:
        await asyncio.to_thread(load_interface_model_cached, path)
    except MaaFWInterfaceLoadError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _open_project(script, path)


@router.post("/editor/script/{script_id}/sync")
async def sync_project(script: ScriptPanel):
    _writable(script)
    record = record_payload(str(script.uid), script)
    context = _checked(
        await client("编辑面板同步项目").call(
            PROJECT_CONTEXT, project_context_request(record)
        )
    )
    if not context["follow_source"] or script.Info.Path is None:
        raise HTTPException(409, "请先启用跟随来源目录")
    if not await asyncio.to_thread(script.Info.Path.is_dir):
        raise HTTPException(422, "MFW 项目来源目录已不存在")
    return await _open_project(script)


async def _open_project(script: MaaFWConfig, source: Path | None = None):
    from .plugin import OWNER

    script_id = str(script.uid)
    opener = ProjectOpener(client("编辑面板准备项目"))

    async def run():
        ticket = await script.try_lock_x()
        if ticket is None:
            raise HTTPException(409, "托管正忙，稍后重试")
        try:
            record = record_payload(script_id, script)
            if source is not None:
                record["source_path"] = str(source)
            refused = await opener.reserve(
                open_request(script_id=script_id, owner=PLUGIN_ID, record=record)
            )
            if refused is not None:
                _checked(refused)
                raise HTTPException(502, "项目服务没有返回作业")
            opened = await opener.prepare()
            patch = dict(opened.record_update or {})
            if source is not None and (patch or opened.kind == "opened"):
                patch["source_path"] = str(source)
            if patch:
                await write_or_raise(OWNER, script_id, patch, holds_lock=True)
            if opened.kind != "opened":
                raise HTTPException(409, opened.reason or "项目操作已停止")
            return {"path": script.Info.Path, "changed": bool(opened.record_update)}
        finally:
            try:
                await opener.release()
            finally:
                await script.unlock(ticket)

    # 完成视图切换和配置写回后再解锁，即使编辑页已关闭。
    work = asyncio.create_task(run())
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        await asyncio.gather(work, return_exceptions=True)
        raise


@router.post("/editor/script/{script_id}/environment")
async def prepare_environment(script: ScriptPanel):
    _writable(script)
    await _root(script)
    request = confirm_request(
        script_id=str(script.uid),
        owner=PLUGIN_ID,
        record=record_payload(str(script.uid), script),
        phase="BeforeRun",
    )
    return _job_result(
        _checked(await client("编辑面板准备环境").run(PROJECT_CONFIRM, request)),
        {"prepared", "prepared_lenient", "unchanged"},
    )


def _job_result(reply: Reply, outcomes: set[str]):
    notice = reply.get("notice")
    message = notice["message"] if notice else None
    if reply.outcome not in outcomes:
        raise HTTPException(409, message or reply.outcome)
    return {"outcome": reply.outcome, "message": message}


class UpdateProjectIn(BaseModel):
    action: Literal["check", "apply"]


@router.post("/editor/script/{script_id}/update")
async def update_project(script: ScriptPanel, payload: UpdateProjectIn):
    _writable(script)
    await _root(script)
    script_id = str(script.uid)
    service = client("编辑面板项目更新")
    record = record_payload(script_id, script)
    if payload.action == "check":
        context = _checked(
            await service.call(PROJECT_CONTEXT, project_context_request(record))
        )
        if context["follow_source"] or script.Update.Source != "GitHub":
            raise HTTPException(409, "当前项目不支持查找可预下载的 GitHub 更新包")
        # 已发布的服务提供全量包发现，独立于托管的自动更新时机。
        record.update(package_mode="full", auto_update_mode="BeforeRun")
        result = _checked(
            await service.run(
                PROJECT_UPDATE_DISCOVER,
                project_job_request(
                    script_id=script_id,
                    owner=PLUGIN_ID,
                    record=record,
                ),
            )
        )
        return {"outcome": "available" if result["downloads"] else "no_download"}
    result = _checked(
        await service.run(
            PROJECT_UPDATE_UPDATE,
            update_request(
                script_id=script_id,
                owner=PLUGIN_ID,
                script_name=script.Info.Name,
                record=record,
                phase="BeforeRun",
            ),
        )
    )
    return _job_result(result, {"updated", "no_update"})


class PackageIn(BaseModel):
    resource: str


@router.post("/editor/script/{script_id}/game-package")
async def game_package(script: ScriptPanel, payload: PackageIn):
    root = await _root(script)

    def resolve():
        try:
            interface = load_interface_model_cached(root)
        except MaaFWInterfaceLoadError as exc:
            raise HTTPException(422, str(exc)) from exc
        return resolve_game_package(
            resource_paths_for(root, interface, payload.resource)
        )

    result = await asyncio.to_thread(resolve)
    return {"package": result.package, "candidates": result.candidates}


@router.get("/editor/user/{script_id}/{user_id}/queues")
async def other_queues(script: UserPanel, user_id: UUID):
    root = await _root(script)
    interface = await asyncio.to_thread(load_interface_model_cached, root)
    fields = password_input_names(interface)
    await Config.get_user(str(script.uid), None)
    queues = []
    for uid, user in script.users.items():
        if uid == user_id:
            continue
        snapshot = json.loads(user.Task.TaskSnapshot)
        snapshot.pop("globalOptions", None)
        snapshot["taskOptions"] = _without_sealed_values(
            map_password_values(snapshot.get("taskOptions", {}), fields, lambda *_: "")
        )
        queues.append({"id": uid, "name": user.Info.Name, "snapshot": snapshot})
    return queues


def _without_sealed_values(value: JsonValue) -> JsonValue:
    # 项目更新删掉了密码字段时，旧快照里仍可能保留该字段的密文。
    if isinstance(value, dict):
        return {key: _without_sealed_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_without_sealed_values(item) for item in value]
    return "" if isinstance(value, str) and is_sealed_secret(value) else value


class QueueTemplate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    snapshot: dict[str, JsonValue]


class SaveTemplatesIn(BaseModel):
    before: str
    templates: list[QueueTemplate]


@router.put("/editor/user/{script_id}/{user_id}/templates")
async def save_templates(script: UserPanel, payload: SaveTemplatesIn):
    _writable(script)
    if len({item.name for item in payload.templates}) != len(payload.templates):
        raise HTTPException(422, "模板名称不能重复")
    templates = []
    if payload.templates:
        root = await _root(script)
        interface = await asyncio.to_thread(load_interface_model_cached, root)
        fields = password_input_names(interface)
        for template in payload.templates:
            snapshot = template.snapshot.copy()
            snapshot.pop("globalOptions", None)
            snapshot["taskOptions"] = _without_sealed_values(
                map_password_values(
                    snapshot.get("taskOptions", {}), fields, lambda *_: ""
                )
            )
            templates.append({"name": template.name, "snapshot": snapshot})
    # 在准备数据后核对现值并提交，避免覆盖另一个账号刚改的模板。
    ticket = await script.try_lock_x(cascade=False)
    if ticket is None:
        raise HTTPException(409, "托管正忙，稍后重试")
    try:
        if script.Task.Templates != payload.before:
            raise HTTPException(409, "模板已在别处修改，请重新加载")
        await script.update(
            MaaFWConfig.model_validate(
                {"Task": {"Templates": json.dumps(templates, ensure_ascii=False)}}
            )
        )
    finally:
        await script.unlock(ticket)
    return {"templates": script.Task.Templates}


@router.post("/editor/script/{script_id}/shell")
async def script_shell_instances(script: ScriptPanel):
    return await list_maafw_shell_instances(
        MaaFWShellInstancesIn(scriptId=str(script.uid))
    )


class ShellImportIn(BaseModel):
    instances: list[str] = Field(min_length=1)


@router.post("/editor/script/{script_id}/shell/import")
async def import_shell_users(script: ScriptPanel, payload: ShellImportIn):
    _writable(script)
    return await import_maafw_shell_instances(
        MaaFWShellInstanceImportIn(
            scriptId=str(script.uid),
            instanceIds=payload.instances,
        )
    )


class ShellPathIn(BaseModel):
    path: str | None = None


@router.post("/editor/user/{script_id}/{user_id}/shell")
async def user_shell_instances(script: UserPanel, payload: ShellPathIn):
    return await list_maafw_shell_instances(
        MaaFWShellInstancesIn(
            scriptId=str(script.uid),
            path=payload.path,
        )
    )


class ShellApplyIn(ShellPathIn):
    instance: str = Field(min_length=1)


@router.post("/editor/user/{script_id}/{user_id}/shell/apply")
async def apply_shell_queue(script: UserPanel, user_id: UUID, payload: ShellApplyIn):
    _writable(script)
    return await apply_maafw_shell_instance(
        MaaFWShellInstanceApplyIn(
            scriptId=str(script.uid),
            userId=str(user_id),
            instanceId=payload.instance,
            path=payload.path,
        )
    )
