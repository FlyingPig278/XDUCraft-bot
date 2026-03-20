from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, to_me

__plugin_meta__ = PluginMetadata(
    name="xducraft_happy_bot",
    description="被@或被回复时自动点表情回应",
    usage="自动触发：@机器人或回复机器人消息；命令：/ans set <emoji_id>（或 /answer set <emoji_id>）",
)

from xducraft_bot.plugins.xducraft_happy_bot.data_manager import get_emoji_id, set_emoji_id
from xducraft_bot.plugins.xducraft_mc_status.utils import is_admin

ANSWER_USAGE = "用法：/ans set <emoji_id>\n示例：/ans set 123"


async def is_reply_to_bot(event: GroupMessageEvent) -> bool:
    if event.reply is None or event.reply.sender is None:
        return False
    return str(event.reply.sender.user_id) == str(event.self_id)

answer_command = on_command(
    "ans",
    aliases={"answer"},
    priority=10,
    block=True,
)


at_me_reply = on_message(
    rule=to_me() | Rule(is_reply_to_bot),
    priority=10,
    block=True
)


@answer_command.handle()
async def handle_answer_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not await is_admin(bot, event):
        await answer_command.finish("你没有执行该命令的权限")

    raw = args.extract_plain_text().strip()
    arg_list = raw.split(maxsplit=1)

    if len(arg_list) != 2 or arg_list[0].lower() != "set":
        await answer_command.finish(ANSWER_USAGE)

    emoji_id = arg_list[1].strip()
    if not emoji_id.isdigit():
        await answer_command.finish("emoji_id 必须是纯数字")

    set_emoji_id(emoji_id)
    await answer_command.finish(f"已将回应表情设置为 emoji_id={emoji_id}")


@at_me_reply.handle()
async def handle_at_me(bot: Bot, event: GroupMessageEvent):
    emoji_id = get_emoji_id()

    await bot.call_api(
        "set_msg_emoji_like",
        message_id=event.message_id,
        emoji_id=emoji_id,
        set=True,
    )
    await at_me_reply.finish()