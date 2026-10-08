"""Business bridge loaded by the bundled bootstrap after runtime activation."""

from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.sv import SV

from Dota2UID.commands import Action, Caller
from Dota2UID.runtime import Runtime
from Dota2UID.replies import ImageReply, Reply
from Dota2UID.subscriptions import SUBSCRIPTION_COMMANDS
from dota2forge_assets import ASSET_COMMANDS
from dota2forge_core import DeliveryOutcome, InvalidIdentityError, SubscriptionEvent

# GsCore resolves the plugin owner from the caller's file. Keep this SV in the
# generated plugins/Dota2UID/_dota2forge_business.py, rather than a runtime wheel.
queries = SV("Dota2UID账号与查询", pm=6)
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


# The bootstrap permanently owns HELP/MENU and forwards them to this handler.
# Registering another blocking HELP handler here would swallow its fallback.
@queries.on_command(
    tuple(action.value for action in Action if action not in {Action.HELP, Action.MENU})
    + SUBSCRIPTION_COMMANDS + ASSET_COMMANDS,
    block=True,
)
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
