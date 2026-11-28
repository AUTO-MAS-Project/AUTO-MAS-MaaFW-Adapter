"""把现有的 MaaFW 账号快照接入宿主的配置恢复块。"""

import asyncio
import json

from auto_mas_core import ConfigRestorePool, RestoreContext
from auto_mas_core.host.utils_common_config.archive import OVERLAY_SIDECAR_NAME
from maafw_adapter_kit.backup_archive import (
    archive_mas_backup,
    build_native_preview,
    build_overlay_preview,
    collect_native_files,
    group_overlay,
    mas_backup_root,
    native_backup_root,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)
from maafw_adapter_kit.services import (
    PROJECT_RUN_RELEASE,
    PROJECT_RUN_RESERVE,
    run_release_request,
    script_request,
)
from maafw_native.layout import view_dir

from .services import client


def _user_overlay(ctx: RestoreContext) -> dict:
    assert ctx.user_id is not None
    return read_overlay_values(ctx.script_config.users[ctx.user_id])


async def _files(ctx: RestoreContext):
    return {
        OVERLAY_SIDECAR_NAME: json.dumps(
            _user_overlay(ctx), ensure_ascii=False, indent=2
        )
    }


async def _root(ctx: RestoreContext):
    assert ctx.user_id is not None
    return mas_backup_root(ctx.script_id, ctx.user_id)


async def _preview(ctx: RestoreContext, timestamp: str):
    assert ctx.user_id is not None
    overlay = await asyncio.to_thread(
        restore_mas_backup, ctx.script_id, ctx.user_id, timestamp
    )
    if overlay is None:
        raise ValueError("备份缺少 MaaFW 账号快照")
    return build_overlay_preview(overlay)


async def _restore(ctx: RestoreContext, timestamp: str):
    assert ctx.user_id is not None
    overlay = await asyncio.to_thread(
        restore_mas_backup, ctx.script_id, ctx.user_id, timestamp
    )
    if overlay is None:
        raise ValueError("备份缺少 MaaFW 账号快照")
    await asyncio.to_thread(
        archive_mas_backup, ctx.script_id, ctx.user_id, _user_overlay(ctx)
    )
    await ctx.config.update_user(ctx.script_id, ctx.user_id, group_overlay(overlay))


async def _native_files(ctx: RestoreContext):
    return await asyncio.to_thread(collect_native_files, view_dir(ctx.script_id))


async def _native_root(ctx: RestoreContext):
    return native_backup_root(ctx.script_id, view_dir(ctx.script_id))


async def _preview_native(ctx: RestoreContext, timestamp: str):
    return await asyncio.to_thread(
        build_native_preview, ctx.script_id, view_dir(ctx.script_id), timestamp
    )


async def _restore_native(ctx: RestoreContext, timestamp: str):
    root = view_dir(ctx.script_id)
    if not root.is_dir():
        raise ValueError("请先导入 MaaFW 项目")
    service = client("恢复项目配置")
    reservation = (
        await service.call(PROJECT_RUN_RESERVE, script_request(ctx.script_id))
    ).expect_ok()
    if reservation.skipped:
        raise ValueError(reservation.message)
    work = asyncio.create_task(
        asyncio.to_thread(restore_native_backup, ctx.script_id, root, timestamp)
    )
    try:
        await asyncio.shield(work)
    except asyncio.CancelledError:
        await asyncio.gather(work, return_exceptions=True)
        raise
    finally:
        (
            await service.call(
                PROJECT_RUN_RELEASE, run_release_request(reservation["key"])
            )
        ).expect_ok()


RESTORE_POOLS = (
    ConfigRestorePool(
        key="mas",
        kind="user",
        editor_scope="user",
        mas_base="user_only",
        files=_files,
        backup_root=_root,
        preview=_preview,
        restore=_restore,
    ),
    ConfigRestorePool(
        key="native",
        kind="script",
        editor_scope="user",
        files=_native_files,
        backup_root=_native_root,
        preview=_preview_native,
        restore=_restore_native,
    ),
)
