"""被 @ 或被回复时贴一个表情回应。

这是一个**被动**功能：没人发指令它也会动。所以默认关闭，只在明确开启的群里
生效——否则机器人一进群就开始给每一条 @ 贴表情。

指令::

    /ans            查看本群当前表情
    /ans set <ID>   设置本群表情
    /ans clear      清除本群设置，回到全局默认
    /ans global set <ID>   设置全局默认（SUPERUSER）
"""

from __future__ import annotations

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.permissions import can_manage, is_superuser

from .data_manager import DEFAULT_EMOJI_ID, clear_group_emoji_id, get_emoji_id, set_emoji_id

__plugin_meta__ = PluginMetadata(
    name="xducraft_happy_bot",
    description="被 @ 或被回复时自动贴表情回应",
    usage="/ans — 查看；/ans set <emoji_id> — 设置本群表情",
)

FEATURE_KEY = "emoji_reaction"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="表情回应",
    description="被 @ 或被回复时自动贴表情",
    default_enabled=False,
    passive=True,
))

ANSWER_USAGE = (
    "用法：\n"
    "/ans — 查看本群当前表情\n"
    "/ans set <emoji_id> — 设置本群表情\n"
    "/ans clear — 回到全局默认\n"
    "/ans global set <emoji_id> — 设置全局默认（超级用户）\n"
    "开关本功能请用 /功能 on 表情回应"
)


async def _is_reply_to_bot(event: GroupMessageEvent) -> bool:
    reply = getattr(event, "reply", None)
    if reply is None or getattr(reply, "sender", None) is None:
        return False
    return str(reply.sender.user_id) == str(event.self_id)


async def _should_react(event: MessageEvent) -> bool:
    """只在启用的群里、且确实被 @ 或被回复时才响应。"""
    if not isinstance(event, GroupMessageEvent):
        return False
    if not feature_gate.is_enabled(FEATURE_KEY, event.group_id):
        return False
    return event.is_tome() or await _is_reply_to_bot(event)


answer_command = on_command("ans", aliases={"answer", "表情回应"}, priority=10, block=True)

# block=False 很重要：这条规则会命中所有 @ 机器人的消息，如果 block=True，
# 优先级更低的插件（词云记录、反撤回缓存）就再也收不到这些消息了。
at_me_reply = on_message(rule=Rule(_should_react), priority=99, block=False)


@answer_command.handle()
async def handle_answer_command(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await answer_command.finish("请在群里使用该命令。")

    tokens = args.extract_plain_text().strip().split()

    if not tokens:
        current = get_emoji_id(event.group_id)
        enabled = feature_gate.is_enabled(FEATURE_KEY, event.group_id)
        await answer_command.finish(
            f"本群表情回应：{'开启' if enabled else '关闭'}\n"
            f"当前表情 ID：{current}\n\n{ANSWER_USAGE}"
        )

    if not await can_manage(bot, event):
        await answer_command.finish("只有群管理员可以修改表情回应设置。")

    action = tokens[0].lower()

    if action == "global":
        if not await is_superuser(bot, event):
            await answer_command.finish("设置全局默认需要超级用户权限。")
        if len(tokens) != 3 or tokens[1].lower() != "set" or not tokens[2].isdigit():
            await answer_command.finish("用法：/ans global set <emoji_id>")
        set_emoji_id(tokens[2], group_id=None)
        await answer_command.finish(f"已将全局默认表情设为 {tokens[2]}。")

    if action == "clear":
        if clear_group_emoji_id(event.group_id):
            await answer_command.finish(f"已清除本群表情设置，回到全局默认 {get_emoji_id()}。")
        await answer_command.finish("本群本来就没有单独设置表情。")

    if action == "set":
        if len(tokens) != 2 or not tokens[1].isdigit():
            await answer_command.finish("emoji_id 必须是纯数字。\n用法：/ans set <emoji_id>")
        set_emoji_id(tokens[1], group_id=event.group_id)
        await answer_command.finish(f"已将本群表情回应设为 emoji_id={tokens[1]}。")

    await answer_command.finish(ANSWER_USAGE)


@at_me_reply.handle()
async def handle_at_me(bot: Bot, event: GroupMessageEvent):
    """贴表情。失败只记日志——协议端不支持这个 API 是很常见的情况，
    不能让它把一条正常消息的处理链打断。"""
    try:
        await bot.call_api(
            "set_msg_emoji_like",
            message_id=event.message_id,
            emoji_id=get_emoji_id(event.group_id) or DEFAULT_EMOJI_ID,
            set=True,
        )
    except Exception as exc:
        logger.debug("[HappyBot] 贴表情失败（协议端可能不支持）: {}", exc)
