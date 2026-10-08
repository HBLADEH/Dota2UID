"""GsCore management bridge usable without installed Dota2Forge packages."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from fastapi import Depends
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core import server, sv
from gsuid_core.sv import Plugins, SV
from gsuid_core.webconsole.app_app import app
from gsuid_core.webconsole.web_api import require_admin_header

from ._dota2forge_runtime import BootstrapError, BundledRuntime

PLUGIN_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "Dota2UID"
BUSINESS_SV = "Dota2UID账号与查询"
FALLBACK = (
    "Dota2UID 运行库尚未可用。请主人发送 do安装核心 准备运行库，"
    "完成后完整重启 GsCore；do核心状态 可查看原因。请勿在聊天中发送 Token。"
)


def valid_arguments(ev: Event) -> bool:
    return (
        isinstance(ev.text, str) and not ev.text.strip()
        and not ev.at_list and ev.at is None
    )


def valid_admin(ev: Event) -> bool:
    return type(ev.user_pm) is int and ev.user_pm == 0 and valid_arguments(ev)


def business_snapshot():
    registry = getattr(sv, "SL", None)
    services = getattr(registry, "lst", {})
    previous = services.get(BUSINESS_SV)
    triggers = {
        kind: dict(items) for kind, items in getattr(previous, "TL", {}).items()
    }
    return previous, triggers


def restore_business(snapshot) -> None:
    """Roll back only this bridge's business SV, preserving management services."""
    registry = getattr(sv, "SL", None)
    services = getattr(registry, "lst", {})
    previous, triggers = snapshot
    candidate = services.get(BUSINESS_SV)
    if candidate is None:
        return
    if previous is not None:
        candidate.TL.clear()
        candidate.TL.update(triggers)
    else:
        candidate.TL.clear()
        services.pop(BUSINESS_SV, None)
        for children in getattr(registry, "detail_lst", {}).values():
            children[:] = [child for child in children if child is not candidate]
    # Recent SDKs cache trigger candidates; older SDKs read TL directly.
    trigger = sys.modules.get("gsuid_core.trigger")
    bump = getattr(trigger, "bump_registry_version", None)
    if bump is not None:
        bump()


class Bootstrap:
    def __init__(self) -> None:
        self.manager = BundledRuntime(PLUGIN_ROOT, DATA_ROOT)
        self.business = None
        self.closed = False
        self.restart_required = False
        self.error = None
        self.started = False
        self.start_task = None
        self.install_task = None
        self.close_task = None
        self.install_lock = asyncio.Lock()
        self.callbacks = {}
        self.registered_hooks = set()

    async def start(self) -> None:
        if self.closed or self.restart_required or self.started:
            return
        self.started = True
        startup = asyncio.create_task(self.start_business())
        self.start_task = startup
        try:
            await asyncio.shield(startup)
        except asyncio.CancelledError:
            startup.cancel()
            while not startup.done():
                try:
                    await asyncio.shield(startup)
                except asyncio.CancelledError:
                    continue
            raise

    async def start_business(self) -> None:
        snapshot = business_snapshot()
        candidate = None
        module_name = __name__ + "._dota2forge_business"
        try:
            generation = await self.manager.prepare(allow_download=False)
            if generation is None or self.closed or self.restart_required:
                return
            self.manager.activate()
            spec = importlib.util.spec_from_file_location(
                module_name, PLUGIN_ROOT / "_dota2forge_business.py"
            )
            if spec is None or spec.loader is None:
                raise ImportError("Missing business bridge")
            candidate = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = candidate
            spec.loader.exec_module(candidate)
            await candidate.start_dota2uid()
            if self.closed:
                await self.discard_business(candidate, module_name, snapshot)
                return
            self.business = candidate
        except asyncio.CancelledError:
            self.error = "cancelled"
            # Preserve ownership until cleanup completes, including repeated
            # cancellation while Runtime.close waits for active sends/workers.
            cleanup = asyncio.create_task(self.discard_business(candidate, module_name, snapshot))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()
            raise
        except BootstrapError as exc:
            self.error = exc.code
            logger.warning(f"Dota2UID runtime unavailable code={exc.code}")
        except Exception:
            self.error = "business_import"
            await self.discard_business(candidate, module_name, snapshot)
            logger.error("Dota2UID business startup failed code=business_import")
        finally:
            self.start_task = None

    async def discard_business(self, candidate, module_name, snapshot) -> None:
        try:
            close = getattr(candidate, "stop_dota2uid", None)
            if close is not None:
                await close()
        except Exception:
            logger.error("Dota2UID business cleanup failed code=business_close")
        finally:
            restore_business(snapshot)
            sys.modules.pop(module_name, None)

    async def install(self, bot: Bot) -> None:
        async with self.install_lock:
            if self.closed:
                await bot.send("Dota2UID 已停用；请完整重启 GsCore 后再安装。")
                return
            if (
                self.install_task is not None and not self.install_task.done()
                or self.start_task is not None and not self.start_task.done()
                or self.manager.state == "preparing"
            ):
                await bot.send("Dota2UID 正在准备运行库；请使用 do核心状态 查看进度。")
                return
            await bot.send("Dota2UID 开始准备运行库；完成后需完整重启 GsCore。")
            self.install_task = asyncio.create_task(self.prepare_install(bot))

    async def prepare_install(self, bot: Bot) -> None:
        try:
            generation = await self.manager.prepare(allow_download=True)
            if self.closed:
                return
            if generation is None:
                await self.send_install_result(bot, self.status_text())
                return
            self.restart_required = True
            self.error = None
            await self.send_install_result(bot, "Dota2UID 运行库已准备；请完整重启 GsCore 后启用。")
        except BootstrapError as exc:
            self.error = exc.code
            if not self.closed:
                await self.send_install_result(bot, self.status_text())
        except Exception:
            self.error = "preparation_failed"
            logger.error("Dota2UID runtime preparation failed code=preparation_failed")
            if not self.closed:
                await self.send_install_result(bot, self.status_text())

    async def send_install_result(self, bot: Bot, text: str) -> None:
        try:
            await bot.send(text)
        except Exception:
            # A chat transport failure must not turn a prepared generation into
            # an installation failure. Its state remains available to diagnostics.
            logger.warning("Dota2UID installation reply failed code=reply_failed")

    async def close(self) -> None:
        if self.close_task is None:
            self.closed = True
            self.close_task = asyncio.create_task(self.finish_close())
        await asyncio.shield(self.close_task)

    async def finish_close(self) -> None:
        await self.manager.close()
        pending = [
            task for task in (self.start_task, self.install_task)
            if task is not None and task is not asyncio.current_task()
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self.business is not None:
            await self.business.stop_dota2uid()

    def status(self) -> dict[str, str | bool]:
        result = dict(self.manager.status())
        result["runtime_state"] = self.manager.state
        result["bootstrap_error"] = self.error or ""
        result["restart_required"] = self.restart_required
        result["client_closed"] = True
        result["business_state"] = "unavailable"
        if self.business is not None:
            runtime = self.business.runtime
            result["business_state"] = runtime.state.value
            result["client_closed"] = runtime.client_closed
            result["assets_state"] = runtime.asset_status.state
        if self.closed:
            result["state"] = "stopped"
        elif self.error == "business_import":
            result["state"] = "business_failed"
        elif self.error == "cancelled":
            result["state"] = "cancelled"
        elif self.restart_required:
            result["state"] = "pending_restart"
        elif self.business is not None:
            result["state"] = self.business.runtime.state.value
        return result

    def status_text(self) -> str:
        text = self.manager.status_text()
        if self.error:
            text += f"\n入口错误：{self.error}。"
        if self.closed:
            return text + "\nDota2UID 已停用，需完整重启 GsCore。"
        if self.restart_required:
            text += "\n运行库待完整重启 GsCore 后启用；热重载不会切换已加载模块。"
        if self.business is not None:
            state = self.business.runtime.state.value
            if state == "awaiting_config":
                text += (
                    "\n业务状态：等待配置（awaiting_config）。请在 data/Dota2UID/config.toml "
                    "填写 STRATZ Token 和部署 namespace，然后按文档停用并重载；"
                    "请勿在聊天中发送 Token。"
                )
            else:
                text += f"\n业务状态：{state}。"
        return text


# GsCore can remove plugin modules without calling shutdown. Keep the lifecycle
# owner outside that namespace so a reload cannot silently replace live clients.
registry_name = "_dota2forge_gscore_bootstrap_owners"
registry = sys.modules.get(registry_name)
if registry is None:
    registry = ModuleType(registry_name)
    registry.owners = {}
    sys.modules[registry_name] = registry
owner_key = str(PLUGIN_ROOT)
owner = registry.owners.get(owner_key)
if owner is not None and (
    owner.closed and owner.close_task is not None and owner.close_task.done()
    and not owner.close_task.cancelled() and owner.close_task.exception() is None
):
    # A completed explicit stop permits a config-only reload. The runtime loader
    # still rejects a different generation if project modules remain in memory.
    for hook_name, collection_name in (
        ("on_core_start_before", "core_start_before_def"),
        ("on_core_start", "core_start_def"),
        ("on_core_shutdown", "core_shutdown_def"),
    ):
        collection = getattr(server, collection_name, None)
        callback = owner.callbacks.get(hook_name)
        if collection is not None:
            stale = [hook for hook in collection if getattr(hook, "func", hook) is callback]
            for hook in stale:
                collection.remove(hook)
    owner = None
if owner is None:
    owner = Bootstrap()
    registry.owners[owner_key] = owner
else:
    owner.restart_required = True

Plugins(name="Dota2UID", prefix=[], allow_empty_prefix=True)
help_service = SV("Dota2UID帮助入口", pm=6)
admin = SV("Dota2UID运行库管理", pm=0)


async def start_dota2uid() -> None:
    await owner.start()


async def stop_dota2uid() -> None:
    await owner.close()


async def help_dota2uid(bot: Bot, ev: Event) -> None:
    if not valid_arguments(ev):
        return
    if owner.business is not None and not owner.closed and not owner.restart_required:
        await owner.business.command_dota2uid(bot, ev)
    else:
        await bot.send(FALLBACK)


async def install_dota2uid(bot: Bot, ev: Event) -> None:
    if valid_admin(ev):
        await owner.install(bot)


async def core_status_dota2uid(bot: Bot, ev: Event) -> None:
    if valid_admin(ev):
        await bot.send(owner.status_text())


async def disable_dota2uid(bot: Bot, ev: Event) -> None:
    if valid_admin(ev):
        await stop_dota2uid()
        await bot.send("Dota2UID 已停用，客户端和运行库准备任务已关闭；现在可重载或卸载插件。")


help_service.on_command(("do帮助", "do菜单"), block=True)(help_dota2uid)
admin.on_command("do安装核心", block=True)(install_dota2uid)
admin.on_command("do核心状态", block=True)(core_status_dota2uid)
admin.on_command("do停用", block=True)(disable_dota2uid)


def ensure_hook(name, callback) -> None:
    callback = owner.callbacks.setdefault(name, callback)
    collection_name = {
        "on_core_start_before": "core_start_before_def",
        "on_core_start": "core_start_def",
        "on_core_shutdown": "core_shutdown_def",
    }[name]
    collection = getattr(server, collection_name, None)
    if collection is not None:
        if any(getattr(hook, "func", hook) is callback for hook in collection):
            return
    elif name in owner.registered_hooks:
        return
    getattr(server, name)(callback)
    owner.registered_hooks.add(name)


ensure_hook("on_core_start_before", start_dota2uid)
ensure_hook("on_core_start", start_dota2uid)
ensure_hook("on_core_shutdown", stop_dota2uid)


async def status_dota2uid() -> dict[str, str | bool]:
    return owner.status()


async def close_dota2uid() -> dict[str, str | bool]:
    await stop_dota2uid()
    return owner.status()


# Remove only our two diagnostic endpoints if a plain module reload did not ask
# the host to remove registrations first; native reload can already remove them.
routes = getattr(getattr(app, "router", None), "routes", None)
if routes is not None:
    routes[:] = [
        route for route in routes
        if not (
            getattr(route, "path", None) in {"/api/dota2uid/status", "/api/dota2uid/stop"}
            and getattr(getattr(route, "endpoint", None), "__module__", None) == __name__
        )
    ]
app.get("/api/dota2uid/status", dependencies=[Depends(require_admin_header)])(status_dota2uid)
app.post("/api/dota2uid/stop", dependencies=[Depends(require_admin_header)])(close_dota2uid)
