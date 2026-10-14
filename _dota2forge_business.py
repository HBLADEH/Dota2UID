"""Business bridge loaded by the bundled bootstrap after runtime activation."""

from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.sv import SV

from Dota2UID.commands import Action, Caller
from Dota2UID.config import ConfigurationError, load_config_values
from Dota2UID.runtime import Runtime
from Dota2UID.replies import ImageReply, Reply
from Dota2UID.subscriptions import GSCORE_SUBSCRIPTION_COMMANDS, SUBSCRIPTION_PATTERN
from dota2forge_assets import ASSET_COMMANDS
from dota2forge_core import DeliveryOutcome, InvalidIdentityError, SubscriptionEvent
from . import settings
from ._dota2forge_config import ConfigBridgeError

HOT_RELOAD_PROTOCOL = 1
enabled = False


def load_host_config(path):
    if settings is None:
        raise ConfigurationError()
    try:
        values = CONFIG_VALUES if "CONFIG_VALUES" in globals() else settings.snapshot()
    except ConfigBridgeError:
        raise ConfigurationError() from None
    return load_config_values(path, values)

# GsCore resolves the plugin owner from the caller's file. Keep this SV in the
# generated plugins/Dota2UID/_dota2forge_business.py, rather than a runtime wheel.
queries = SV("Dota2UID账号与查询", pm=6)
runtime = Runtime(
    Path(__file__).resolve().parents[3] / "data" / "Dota2UID" / "config.toml",
    config_loader=load_host_config,
)
JOB_ID = "Dota2UID-subscriptions"
job_registered = False
native_ai = None


async def send_subscription(event: SubscriptionEvent, replies: tuple[Reply, ...]) -> DeliveryOutcome:
    from gsuid_core.config import core_config
    from gsuid_core.gss import gss
    from gsuid_core.models import Message

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
    if not replies:
        return DeliveryOutcome.NOT_ATTEMPTED
    messages = [
        Message(type="image", data=reply.artifact.data)
        if isinstance(reply, ImageReply) else Message(type="text", data=reply.text + "\n")
        for reply in replies
    ]
    try:
        receipt = await bot.target_send(
            messages, caller.conversation_kind, caller.conversation_id,
            caller.platform_key, caller.bot_self_id, wait_recall=True,
        )
    except (OSError, TimeoutError, RuntimeError):
        return DeliveryOutcome.UNCERTAIN
    return (DeliveryOutcome.ACCEPTED if isinstance(receipt, list) and receipt
            and all(isinstance(value, str) and value for value in receipt)
            else DeliveryOutcome.UNCERTAIN)


async def poll_subscriptions() -> None:
    await runtime.poll_subscriptions(send_subscription)


async def start_dota2uid() -> None:
    global job_registered, enabled, native_ai
    await runtime.start()
    if native_ai is None:
        # The active runtime wheel is frozen with this generation. Loading its
        # fixed bridge resource avoids retaining a previous generation's Core
        # exception/tool classes in an external, cached plugin helper module.
        from importlib.resources import files
        native_source = files("Dota2UID").joinpath("host_ai.py.template").read_text("utf-8")
        native_namespace = {"__name__": __name__, "__file__": __file__}
        exec(compile(native_source, __file__, "exec"), native_namespace)
        native_ai = native_namespace["register_native_ai"](runtime, caller_from_event)
    enabled = runtime.state.value in {"ready", "awaiting_config"}
    if runtime.state.value == "ready" and runtime.subscriptions_enabled:
        from gsuid_core.aps import scheduler
        if scheduler.get_job(JOB_ID) is None:
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
    global job_registered, enabled, native_ai
    enabled = False
    if job_registered:
        from gsuid_core.aps import scheduler
        if scheduler.get_job(JOB_ID) is not None:
            scheduler.remove_job(JOB_ID)
        job_registered = False
    if native_ai is not None:
        await native_ai.close()
        native_ai = None
    await runtime.close()
    logger.info(
        f"Dota2UID stopped state={runtime.state.value} client_closed={runtime.client_closed} "
        f"job_registered={job_registered}"
    )


# The bootstrap permanently owns HELP/MENU and forwards them to this handler.
# Registering another blocking HELP handler here would swallow its fallback.
@queries.on_command(
    tuple(action.value for action in Action if action not in {Action.HELP, Action.MENU})
    + GSCORE_SUBSCRIPTION_COMMANDS + ASSET_COMMANDS,
    block=True,
)
@queries.on_regex(r"^do(?P<hero>.{1,64})出装$", block=True)
@queries.on_regex(r"^do(?P<guide_hero>.{1,64})攻略(?:\s+(?P<guide_args>.{1,80}))?$", block=True)
@queries.on_regex(SUBSCRIPTION_PATTERN, block=True)
async def command_dota2uid(bot: Bot, ev: Event) -> None:
    if not enabled:
        return
    caller = Caller(
        ev.bot_id, ev.bot_self_id, ev.user_id, ev.WS_BOT_ID,
        bool(ev.at_list) or ev.at is not None,
        ev.user_type, ev.group_id,
        type(ev.user_pm) is int and ev.user_pm == 0,
    )
    async def send(reply: Reply) -> object:
        return await bot.send(reply.artifact.data if isinstance(reply, ImageReply) else reply.text)
    if ev.command == "do复盘" and native_ai is not None:
        if await native_ai.review(bot, ev, ev.text):
            return
    guide_hero = ev.regex_dict.get("guide_hero")
    if guide_hero:
        await runtime.dispatch(caller, "do攻略", guide_hero + " " + (ev.regex_dict.get("guide_args") or ""), send)
        return
    hero = ev.regex_dict.get("hero")
    subscription_args = ev.regex_dict.get("subscription_args")
    if subscription_args is not None:
        await runtime.dispatch(caller, "do订阅", subscription_args, send)
    else:
        await runtime.dispatch(caller, "do出装" if hero else ev.command, hero if hero else ev.text, send)


def caller_from_event(ev):
    return Caller(ev.bot_id, ev.bot_self_id, ev.user_id, ev.WS_BOT_ID,
                  any(str(value) != str(ev.bot_self_id) for value in ev.at_list)
                  or (ev.at is not None and str(ev.at) != str(ev.bot_self_id)),
                  ev.user_type, ev.group_id,
                  type(ev.user_pm) is int and ev.user_pm == 0)
