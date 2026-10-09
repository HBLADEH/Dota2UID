"""GsCore management bridge usable without installed Dota2Forge packages."""

import asyncio
import copy
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

from ._dota2forge_runtime import (
    BootstrapError,
    BundledRuntime,
    RuntimeSwitch,
    claim_runtime,
    storage_fingerprint,
)
from ._dota2forge_config import ConfigBridgeError, protect_config_traces, register_config

PLUGIN_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "Dota2UID"
try:
    protect_config_traces(app)
    settings = register_config(DATA_ROOT)
except ConfigBridgeError:
    settings = None
    logger.warning("Dota2UID configuration unavailable code=config_storage")
BUSINESS_SV = "Dota2UID账号与查询"
FALLBACK = (
    "Dota2UID 运行库尚未可用。请主人发送 do安装核心 准备运行库，"
    "完成后重载插件；do核心状态 可查看原因。请勿在聊天中发送 Token。"
)
HOT_RELOAD_PROTOCOL = 1
CLOSE_TIMEOUT = 30.0


def valid_arguments(ev: Event) -> bool:
    return isinstance(ev.text, str) and not ev.text.strip() and not ev.at_list and ev.at is None


def valid_admin(ev: Event) -> bool:
    return type(ev.user_pm) is int and ev.user_pm == 0 and valid_arguments(ev)


def business_snapshot():
    registry = getattr(sv, "SL", None)
    services = getattr(registry, "lst", {})
    previous = services.get(BUSINESS_SV)
    triggers = {kind: dict(items) for kind, items in getattr(previous, "TL", {}).items()}
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
    protocol = HOT_RELOAD_PROTOCOL

    def __init__(self, previous=None) -> None:
        self.manager = BundledRuntime(PLUGIN_ROOT, DATA_ROOT)
        self.business = None
        self.active_manager = None
        self.active_source = None
        self.active_config = None
        self.previous = previous
        self.legacy = previous is not None and (
            getattr(previous, "protocol", None) != HOT_RELOAD_PROTOCOL
            or getattr(previous, "legacy", False)
            or getattr(previous, "restart_required", False)
        )
        self.closed = False
        self.restart_required = self.legacy
        self.error = None
        self.started = False
        self.start_task = None
        self.install_task = None
        self.close_task = None
        self.install_lock = asyncio.Lock()
        self.callbacks = {}
        self.registered_hooks = set()
        self.switch_state = "idle"
        self.pending_reload = False
        self.config_values = None
        self.source = None
        try:
            self.manager.freeze()
            self.source = self.manager.bridge
            if settings is not None:
                self.config_values = copy.deepcopy(settings.snapshot())
        except (BootstrapError, OSError, ConfigBridgeError):
            self.error = "invalid_manifest"
        if self.legacy:
            self.business = previous.business
            self.error = "reload_incompatible"

    async def start(self) -> None:
        if self.closed or self.restart_required or self.started or self.pending_reload:
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
        try:
            async with registry.operation_lock:
                if self.closed or registry.owners.get(owner_key) is not self:
                    return
                await self.transition()
        except asyncio.CancelledError:
            self.error = "cancelled"
            raise
        except BootstrapError as exc:
            self.error = exc.code
            logger.warning(f"Dota2UID runtime unavailable code={exc.code}")
        except Exception:
            self.error = "business_import"
            logger.error("Dota2UID business startup failed code=business_import")
        finally:
            self.start_task = None

    async def transition(self) -> None:
        previous = self.previous
        # A rapid sequence can leave an unstarted owner between us and the active
        # owner. Never lose the reference to that still-live lifecycle.
        while previous is not None and previous.business is None and previous.previous is not None:
            previous = previous.previous
        self.previous = previous
        snapshot = business_snapshot()
        candidate = None
        transaction = None
        fingerprint = None
        previous_closed = False
        try:
            self.switch_state = "preparing"
            if self.error is not None:
                raise BootstrapError(self.error)
            generation = await self.manager.prepare(allow_download=False)
            if generation is None:
                raise BootstrapError(self.manager.error or "preparation_failed")
            if self.closed or registry.owners.get(owner_key) is not self:
                return
            if previous is not None and previous.active_manager is not None:
                transaction = RuntimeSwitch(
                    previous.active_manager,
                    self.manager,
                    owner_key,
                    __name__,
                )
                fingerprint = storage_fingerprint(DATA_ROOT)
                self.switch_state = "closing"
                previous_closed = True
                closing = asyncio.create_task(previous.close())
                done, _ = await asyncio.wait({closing}, timeout=CLOSE_TIMEOUT)
                if not done:
                    self.restart_required = True
                    raise BootstrapError("close_timeout")
                closing.result()
                if self.closed or registry.owners.get(owner_key) is not self:
                    return
                # Recheck the persisted schema after all old transactions exited.
                fingerprint = storage_fingerprint(DATA_ROOT)
                transaction.detach()
            self.switch_state = "loading"
            self.manager.activate()
            claim_runtime(self.manager, owner_key)
            candidate = await self.load_business(self.source, self.config_values)
            if self.closed or registry.owners.get(owner_key) is not self:
                raise BootstrapError("superseded")
            self.business = candidate
            self.active_manager = self.manager
            self.active_source, self.active_config = self.source, self.config_values
            if hasattr(candidate, "runtime"):
                await candidate.start_dota2uid()
            self.manager.record_active()
            self.error = None
            self.previous = None
            self.switch_state = "idle"
        except BaseException as exc:
            code = (
                exc.code
                if isinstance(exc, BootstrapError)
                else ("cancelled" if isinstance(exc, asyncio.CancelledError) else "business_import")
            )
            self.error = code
            # Cleanup remains owned even if GsCore cancels the previous hook's
            # waiter several times during another native reload.
            cleanup = asyncio.create_task(
                self.recover(
                    candidate,
                    snapshot,
                    transaction,
                    previous,
                    previous_closed,
                    fingerprint,
                )
            )
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning(f"Dota2UID runtime unavailable code={self.error}")

    async def load_business(self, source, values):
        module_name = __name__ + "._dota2forge_business"
        path = PLUGIN_ROOT / "_dota2forge_business.py"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None or source is None:
            raise ImportError("Missing frozen business bridge")
        candidate = importlib.util.module_from_spec(spec)
        candidate.CONFIG_VALUES = copy.deepcopy(values)
        sys.modules[module_name] = candidate
        try:
            exec(compile(source, str(path), "exec", dont_inherit=True), candidate.__dict__)
            if hasattr(candidate, "runtime"):
                await candidate.runtime.start()
                if candidate.runtime.state.value not in {"ready", "awaiting_config"}:
                    raise BootstrapError("business_start")
            else:
                await candidate.start_dota2uid()
            return candidate
        except BaseException:
            # Expose the partial candidate to the owned recovery path.
            self.partial_business = candidate
            raise

    async def recover(
        self, candidate, snapshot, transaction, previous, previous_closed, fingerprint
    ):
        candidate = candidate or getattr(self, "partial_business", None)
        await self.discard_business(candidate, __name__ + "._dota2forge_business", snapshot)
        self.business = None
        self.active_manager = None
        if previous is None:
            self.switch_state = "failed"
            return
        if not previous_closed:
            self.adopt(previous)
            await self.restore_live_business()
            self.switch_state = "retained"
            return
        if transaction is None or not transaction.detached or self.error == "close_timeout":
            self.restart_required = True
            self.switch_state = "failed"
            return
        try:
            if storage_fingerprint(DATA_ROOT) != fingerprint:
                raise BootstrapError("storage_changed")
            transaction.restore()
            if self.closed:
                self.switch_state = "stopped"
                return
            self.active_source, self.active_config = previous.active_source, previous.active_config
            self.business = await self.load_business(self.active_source, self.active_config)
            self.active_manager = previous.active_manager
            await self.business.start_dota2uid()
            self.active_manager.record_active()
            self.switch_state = "rolled_back"
            self.previous = None
        except BaseException as failure:
            self.error = failure.code if isinstance(failure, BootstrapError) else "rollback_failed"
            await self.discard_business(
                self.business or getattr(self, "partial_business", None),
                __name__ + "._dota2forge_business",
                business_snapshot(),
            )
            self.business = None
            self.restart_required = True
            self.switch_state = "failed"

    def adopt(self, previous) -> None:
        self.business = previous.business
        self.active_manager = previous.active_manager
        self.active_source, self.active_config = previous.active_source, previous.active_config
        self.previous = None
        # The registry's new owner now holds the still-live resources. Keep the
        # old callbacks harmless without closing the adopted business.
        previous.business = None

    async def restore_live_business(self) -> None:
        if self.business is None:
            return
        service = SV(BUSINESS_SV, pm=6)
        triggers = {key: dict(value) for key, value in self.business.queries.TL.items()}
        service.TL.clear()
        service.TL.update(triggers)
        await self.business.start_dota2uid()

    async def discard_business(self, candidate, module_name, snapshot) -> None:
        try:
            close = getattr(candidate, "stop_dota2uid", None)
            if close is not None:
                await close()
        except Exception:
            self.error = "business_close"
            self.restart_required = True
            self.switch_state = "failed"
            logger.error("Dota2UID business cleanup failed code=business_close")
            raise BootstrapError("business_close") from None
        finally:
            restore_business(snapshot)
            sys.modules.pop(module_name, None)

    async def install(self, bot: Bot) -> None:
        async with self.install_lock:
            if self.closed:
                await bot.send("Dota2UID 已停用；请完整重启 GsCore 后再安装。")
                return
            if (
                self.install_task is not None
                and not self.install_task.done()
                or self.start_task is not None
                and not self.start_task.done()
                or self.manager.state == "preparing"
            ):
                await bot.send("Dota2UID 正在准备运行库；请使用 do核心状态 查看进度。")
                return
            await bot.send("Dota2UID 开始准备运行库；完成后请重载插件。")
            self.install_task = asyncio.create_task(self.prepare_install(bot))

    async def prepare_install(self, bot: Bot) -> None:
        try:
            async with registry.operation_lock:
                if self.closed or registry.owners.get(owner_key) is not self:
                    return
                if self.active_manager is self.manager:
                    self.manager = BundledRuntime(PLUGIN_ROOT, DATA_ROOT)
                    self.manager.freeze()
                generation = await self.manager.prepare(allow_download=True)
            if self.closed:
                return
            if generation is None:
                await self.send_install_result(bot, self.status_text())
                return
            self.error = None
            self.pending_reload = True
            await self.send_install_result(
                bot, "Dota2UID 运行库已准备；请重载插件启用，do核心状态 可确认实际版本。"
            )
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
            task
            for task in (self.start_task, self.install_task)
            if task is not None and task is not asyncio.current_task()
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self.business is not None:
            await self.business.stop_dota2uid()
        elif getattr(self, "partial_business", None) is not None:
            close = getattr(self.partial_business, "stop_dota2uid", None)
            if close is not None:
                await close()
        if self.previous is not None:
            await self.previous.close()

    def status(self) -> dict[str, str | bool]:
        result = dict(self.manager.status())
        result["runtime_state"] = self.manager.state
        result["bootstrap_error"] = self.error or ""
        result["restart_required"] = self.restart_required
        result["client_closed"] = True
        result["business_state"] = "unavailable"
        result["configuration_available"] = settings is not None
        result["switch_state"] = self.switch_state
        result["expected_versions"] = str(self.manager.versions)
        result["expected_manifest"] = self.manager.digest
        result["prepared_versions"] = str(self.manager.versions) if self.manager.generation else ""
        result["prepared_manifest"] = self.manager.digest if self.manager.generation else ""
        active_owner = self
        while active_owner.business is None and active_owner.previous is not None:
            active_owner = active_owner.previous
        active = self.active_manager or active_owner.active_manager
        active_business = self.business or active_owner.business
        result["active_versions"] = str(active.versions) if active else ""
        result["active_manifest"] = active.digest if active else ""
        if active_business is not None:
            runtime = active_business.runtime
            result["business_state"] = runtime.state.value
            result["client_closed"] = runtime.client_closed
            result["assets_state"] = runtime.asset_status.state
        if self.closed:
            result["state"] = "stopped"
        elif self.switch_state in {"preparing", "closing", "loading"}:
            result["state"] = "switching"
        elif self.error == "business_import":
            result["state"] = "business_failed"
        elif self.error == "cancelled":
            result["state"] = "cancelled"
        elif self.switch_state == "failed" and not self.restart_required:
            result["state"] = "failed"
        elif self.restart_required:
            result["state"] = "pending_restart"
        elif self.pending_reload:
            result["state"] = "pending_reload"
        elif self.business is not None:
            result["state"] = self.business.runtime.state.value
        return result

    def status_text(self) -> str:
        text = self.manager.status_text()
        active_owner = self
        while active_owner.business is None and active_owner.previous is not None:
            active_owner = active_owner.previous
        active = self.active_manager or active_owner.active_manager
        active_business = self.business or active_owner.business
        if settings is None:
            text += "\n配置文件无法读取，请管理员按配置指南修复；原文件已保留。"
        if self.error:
            text += f"\n入口错误：{self.error}。"
        if self.closed:
            return text + "\nDota2UID 已停用，需完整重启 GsCore。"
        if self.restart_required:
            text += "\n当前情况不能安全热切换，请完整重启 GsCore。"
        elif self.pending_reload:
            text += "\n运行库已准备，重载插件后启用。"
        text += "\n期望版本：" + str(self.manager.versions)
        text += "\n运行版本：" + (str(active.versions) if active else "未启用")
        text += "\n期望摘要：" + self.manager.digest[:12]
        if active:
            text += "\n运行摘要：" + active.digest[:12]
        text += "\n切换状态：" + self.switch_state
        if active_business is not None:
            state = active_business.runtime.state.value
            if state == "awaiting_config":
                text += (
                    "\n业务状态：等待配置（awaiting_config）。请在后台插件配置 → Dota2UID "
                    "填写 STRATZ Token 和部署 namespace，确认修改后 do停用，再重载当前插件；"
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
if not hasattr(registry, "operation_lock"):
    registry.operation_lock = asyncio.Lock()
owner_key = str(PLUGIN_ROOT)
previous_owner = registry.owners.get(owner_key)
if previous_owner is not None:
    for hook_name, collection_name in (
        ("on_core_start_before", "core_start_before_def"),
        ("on_core_start", "core_start_def"),
        ("on_core_shutdown", "core_shutdown_def"),
    ):
        collection = getattr(server, collection_name, None)
        callback = previous_owner.callbacks.get(hook_name)
        if collection is not None:
            stale = [hook for hook in collection if getattr(hook, "func", hook) is callback]
            for hook in stale:
                collection.remove(hook)
owner = Bootstrap(previous_owner)
registry.owners[owner_key] = owner

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
        route
        for route in routes
        if not (
            getattr(route, "path", None) in {"/api/dota2uid/status", "/api/dota2uid/stop"}
            and getattr(getattr(route, "endpoint", None), "__module__", None) == __name__
        )
    ]
app.get("/api/dota2uid/status", dependencies=[Depends(require_admin_header)])(status_dota2uid)
app.post("/api/dota2uid/stop", dependencies=[Depends(require_admin_header)])(close_dota2uid)
