from ._dota2forge_bootstrap import verify_dependencies as _verify_dependencies

_verify_dependencies(__file__)

"""GsCore discovery bridge; install as plugins/Dota2UID/__init__.py."""

from pathlib import Path

from fastapi import Depends
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.server import on_core_shutdown, on_core_start, on_core_start_before
from gsuid_core.sv import Plugins, SV
from gsuid_core.webconsole.app_app import app
from gsuid_core.webconsole.web_api import require_admin_header

from Dota2UID.commands import Action, Caller
from Dota2UID.runtime import Runtime
from Dota2UID.replies import ImageReply, Reply
from Dota2UID.subscriptions import SUBSCRIPTION_COMMANDS
from dota2forge_core import DeliveryOutcome, InvalidIdentityError, SubscriptionEvent

Plugins(name="Dota2UID", prefix=[], allow_empty_prefix=True)
queries = SV("Dota2UID账号与查询", pm=6)
admin = SV("Dota2UID生命周期", pm=0)
runtime = Runtime(Path(__file__).resolve().parents[3] / "data" / "Dota2UID" / "config.toml")
JOB_ID = "Dota2UID-subscriptions"
job_registered = False


async def send_subscription(event: SubscriptionEvent, text: str) -> DeliveryOutcome:
    from gsuid_core.config import core_config
    from gsuid_core.gss import gss

    try:
        caller = runtime.subscription_route(event)
    except InvalidIdentityError:
        return DeliveryOutcome.NOT_ATTEMPTED
    if caller.connection_id not in gss.active_ws:
        return DeliveryOutcome.NOT_ATTEMPTED
    bot = gss.active_bot.get(caller.connection_id)
    if bot is None:
        return DeliveryOutcome.NOT_ATTEMPTED
    if caller.conversation_kind == "group" and caller.user_id not in {
        str(value) for value in core_config.get_config("masters")
    }:
        return DeliveryOutcome.NOT_ATTEMPTED
    try:
        receipt = await bot.target_send(
            text, caller.conversation_kind, caller.conversation_id,
            caller.platform_key, caller.bot_self_id, wait_recall=True,
        )
    except (OSError, TimeoutError, RuntimeError):
        return DeliveryOutcome.UNCERTAIN
    return DeliveryOutcome.ACCEPTED if receipt else DeliveryOutcome.UNCERTAIN


async def poll_subscriptions() -> None:
    await runtime.poll_subscriptions(send_subscription)


@on_core_start_before
@on_core_start
async def start_dota2uid() -> None:
    global job_registered
    await runtime.start()
    if runtime.state.value == "ready" and runtime.subscriptions_enabled and not job_registered:
        from gsuid_core.aps import scheduler
        scheduler.add_job(
            poll_subscriptions, "interval", seconds=60, id=JOB_ID,
            max_instances=1, coalesce=True, replace_existing=True,
        )
        job_registered = True
    logger.info(
        f"Dota2UID initialized state={runtime.state.value} "
        f"subscriptions_enabled={runtime.subscriptions_enabled} job_registered={job_registered}"
    )


@on_core_shutdown
async def stop_dota2uid() -> None:
    global job_registered
    if job_registered:
        from gsuid_core.aps import scheduler
        if scheduler.get_job(JOB_ID) is not None:
            scheduler.remove_job(JOB_ID)
        job_registered = False
    await runtime.close()
    logger.info(
        f"Dota2UID stopped state={runtime.state.value} client_closed={runtime.client_closed} "
        f"job_registered={job_registered}"
    )


@queries.on_command(tuple(action.value for action in Action) + SUBSCRIPTION_COMMANDS, block=True)
@queries.on_regex(r"^do(?P<hero>.{1,64})出装$", block=True)
async def command_dota2uid(bot: Bot, ev: Event) -> None:
    caller = Caller(
        ev.bot_id, ev.bot_self_id, ev.user_id, ev.WS_BOT_ID,
        bool(ev.at_list) or ev.at is not None,
        ev.user_type, ev.group_id,
        type(ev.user_pm) is int and ev.user_pm == 0,
    )
    async def send(reply: Reply) -> object:
        return await bot.send(reply.artifact.data if isinstance(reply, ImageReply) else reply.text)
    hero = ev.regex_dict.get("hero")
    await runtime.dispatch(caller, "do出装" if hero else ev.command, hero if hero else ev.text, send)


@admin.on_command("do停用", block=True)
async def disable_dota2uid(bot: Bot, ev: Event) -> None:
    if type(ev.user_pm) is not int or ev.user_pm != 0 or ev.text.strip() or ev.at_list:
        return
    await stop_dota2uid()
    await bot.send("Dota2UID 已停用，客户端已关闭；现在可重载或卸载插件。")


@app.get("/api/dota2uid/status", dependencies=[Depends(require_admin_header)])
async def status_dota2uid() -> dict[str, str | bool]:
    return {"state": runtime.state.value, "client_closed": runtime.client_closed}


@app.post("/api/dota2uid/stop", dependencies=[Depends(require_admin_header)])
async def close_dota2uid() -> dict[str, str | bool]:
    await stop_dota2uid()
    return await status_dota2uid()
