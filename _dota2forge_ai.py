"""Native GsCore tools and per-turn hints; imported only by discovery bridges."""

import asyncio
import json

from dota2forge_core import Dota2ForgeError
from dota2forge_core.feature_tools import TOOL_NAMES


def register_review_skill():
    """Own one SDK skill registration; older SDKs still receive tool guidance."""
    try:
        from gsuid_core.ai_core.register import ai_skill
        from gsuid_core.ai_core.skills.operations import _rebuild_skills
        from gsuid_core.ai_core.skills.resource import plugin_skill_dirs
    except ImportError:
        return lambda: None
    from dota2forge_core.infrastructure.review_guidance import skill_directory
    root = skill_directory().resolve()
    if not isinstance(plugin_skill_dirs, list) or not callable(_rebuild_skills):
        return lambda: None
    ai_skill(root, plugin="Dota2UID")
    owned = next((entry for entry in plugin_skill_dirs
                  if entry == (root, "Dota2UID")), None)

    def release():
        # Current SDK has no public unregister. Remove only this exact generation's tuple.
        for index, entry in enumerate(plugin_skill_dirs):
            if entry is owned:
                plugin_skill_dirs.pop(index)
                _rebuild_skills()
                break

    return release


def register_native_ai(runtime, caller_from_event):
    try:
        from gsuid_core.ai_core.configs.ai_config import ai_config
        from gsuid_core.ai_core.hooks import AgentHookPoint, on_agent_hook
        from gsuid_core.ai_core.models import ToolContext
        from gsuid_core.ai_core.register import ai_tools
        from gsuid_core.ai_core.session_registry import get_ai_session_registry
        from gsuid_core.utils.resource_manager import RM
        if not ai_config.get_config("enable").data:
            return None
    except ImportError:
        return None

    owned = set()

    def scope(ctx):
        if ctx.ev is None or not ctx.parent_session_id or not ctx.allow_user_outbound:
            raise ValueError("Main native chat context is required")
        session = get_ai_session_registry().get_ai_session(ctx.parent_session_id)
        if session is None:
            raise ValueError("Native conversation was reset")
        return caller_from_event(ctx.ev), ctx.parent_session_id, session

    async def call(ctx, name, args):
        try:
            tool_scope = getattr(ctx, "tool_scope", None)
            if tool_scope is not None and not tool_scope.plugin_enabled("Dota2UID"):
                return '{"error":"tool_disabled_by_persona"}'
            if name in getattr(ctx, "blocked_tool_names", set()):
                return '{"error":"tool_disabled_by_native_scope"}'
            caller, session_id, generation = scope(ctx)
            payload, artifact = await runtime.ai_tool(caller, session_id, generation, name, args)
            if artifact is not None:
                payload["image_resource_id"] = RM.register(artifact.data)
                payload["image_delivery"] = (
                    "尚未发送；需要图片时用宿主 send_message_by_ai 的 image_id 发送一次。"
                    "这些文字事实已经随工具结果进入当前会话，无需 OCR 或再添加历史。"
                )
            return json.dumps(payload, ensure_ascii=False)
        except Dota2ForgeError as error:
            return json.dumps({"error": type(error).__name__, "code": getattr(error, "code", "invalid_context"),
                               "source": getattr(error, "source", None)}, ensure_ascii=False)
        except ValueError:
            return '{"error":"invalid_arguments_or_native_session"}'

    async def get_dota2_meta(ctx: ToolContext, position: int = 0, rank: str = "ALL",
                            days: int = 7, sort: str = "reliable"):
        """Dota2 当前版本强势英雄；带窗口、位置、段位、样本和可靠度，非上分保证。

        Args:
            position: 0为全部位置，1到5为指定位置。
            rank: ALL或HERALD/GUARDIAN/CRUSADER/ARCHON/LEGEND/ANCIENT/DIVINE/IMMORTAL。
            days: 7或14，来源缺日明确标注。
            sort: reliable或win_rate。
        """
        return await call(ctx, "get_dota2_meta", {"position": position, "rank": rank, "days": days, "sort": sort})

    async def get_dota2_hero_guide(ctx: ToolContext, hero_name: str, position: int = 1,
                                  match_id: str = ""):
        """Dota2 英雄攻略观察；指定比赛时返回单场升级/购买样例，不混为聚合推荐。

        Args:
            hero_name: 英雄中文名、英文名或简称。
            position: 1到5号位。
            match_id: 可选规范十进制比赛ID，留空查询聚合攻略。
        """
        return await call(ctx, "get_dota2_hero_guide", {"hero_name": hero_name, "position": position, "match_id": match_id})

    async def get_dota2_review_context(ctx: ToolContext, match_id: str = "",
                                      hero_name: str = "", topic: str = "overview"):
        """Dota2 比赛复盘事实。后续为什么、出装等追问可省略ID，沿用当前可信会话定位。

        Args:
            match_id: 可选比赛ID；首次未定位时必须提供。
            hero_name: 可选本场英雄；留空使用当前视角或本人绑定偏好。
            topic: overview/economy/items/laning/team。
        """
        return await call(ctx, "get_dota2_review_context", {"match_id": match_id, "hero_name": hero_name, "topic": topic})

    async def render_dota2_review_data(ctx: ToolContext, kind: str, match_id: str = "",
                                      hero_name: str = "", start_seconds: int = 0,
                                      end_seconds: int = 0):
        """按需生成 Dota2 数据补图；仅来源曲线/购买记录，无AI编造图。返回资源后发送一次。

        Args:
            kind: economy/team_advantage/items三种之一。
            match_id: 可选；沿用当前复盘定位。
            hero_name: 可选本场英雄。
            start_seconds: 比赛秒数，可包含赛前负时间，最低-600。
            end_seconds: 区间结束秒数，0使用比赛实际时长。
        """
        args = {"kind": kind, "match_id": match_id, "hero_name": hero_name, "start_seconds": start_seconds}
        if end_seconds != 0:
            args["end_seconds"] = end_seconds
        return await call(ctx, "render_dota2_review_data", args)

    functions = (get_dota2_meta, get_dota2_hero_guide, get_dota2_review_context, render_dota2_review_data)
    for func in functions:
        def visible(ctx, name=func.__name__):
            tool_scope = getattr(ctx.deps, "tool_scope", None)
            return (tool_scope is None or tool_scope.plugin_enabled("Dota2UID")) and name not in getattr(ctx.deps, "blocked_tool_names", set())
        ai_tools(category="common", capability_domain="dota2", context_tags=["dota2"],
                 aliases=["Dota2", "刀塔", "版本强势", "英雄攻略", "比赛复盘"],
                 covers=["Dota2英雄和比赛的来源数据查询、复盘数据图"],
                 visible_when=visible, timeout=60)(func)

    def hint(ctx):
        if ctx.ev is None or ctx.is_subagent or ctx.is_framework:
            return None
        from gsuid_core.ai_core.agent_node.tool_scope import get_tool_scope
        if not get_tool_scope(ctx.persona_name).plugin_enabled("Dota2UID"):
            return None
        generation = get_ai_session_registry().get_ai_session(ctx.session_id)
        if generation is None:
            return None
        history = getattr(generation, "history", ())
        # H14 does not populate query; use the same trusted event as normal chat.
        query = ctx.query or ctx.ev.raw_text
        return runtime.review_hint(caller_from_event(ctx.ev), ctx.session_id, generation,
                                   query, len(history))

    @on_agent_hook(AgentHookPoint.AFTER_CONTEXT, priority=420)
    async def review_context_hint(ctx):
        text = hint(ctx)
        if text:
            ctx.append_user_hint(text)

    @on_agent_hook(AgentHookPoint.ASSEMBLE_TOOLS, priority=420)
    async def review_tools(ctx):
        if hint(ctx):
            ctx.ensure_tools("get_dota2_review_context", "render_dota2_review_data")

    release_skill = register_review_skill()

    class NativeAI:
        async def review(self, bot, ev, text):
            from gsuid_core.ai_core.ai_router import get_ai_session
            from gsuid_core.ai_core.handle_ai import handle_ai_chat
            if not ai_config.get_config("enable").data:
                return False
            try:
                session = await get_ai_session(ev)
            except ValueError:
                return False
            task = asyncio.current_task()
            if task is not None:
                owned.add(task)
            try:
                await runtime.begin_review(caller_from_event(ev), ev.session_id, session, text)
                await handle_ai_chat(bot, ev)
                return True
            except Dota2ForgeError as error:
                await bot.send("复盘数据获取失败：" + str(getattr(error, "code", "invalid_context")) + "。请核实参数或稍后手动再试。")
                return True
            except ValueError:
                await bot.send("复盘参数不正确，请使用 do复盘 <比赛ID> [英雄]。")
                return True
            finally:
                if task is not None:
                    owned.discard(task)

        async def close(self):
            from gsuid_core.ai_core.hooks import drop_hooks_for_module
            from gsuid_core.ai_core.register import unregister_tool
            for name in TOOL_NAMES:
                unregister_tool(name)
            drop_hooks_for_module(__name__)
            release_skill()
            tasks = tuple(task for task in owned if task is not asyncio.current_task())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return NativeAI()
