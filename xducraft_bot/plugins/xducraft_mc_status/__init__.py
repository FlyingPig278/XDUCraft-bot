"""XDUCraft Minecraft 服务器状态查询。

``/mcs`` 的统一入口。真正的子命令实现都在 :mod:`.handlers`。
"""

from __future__ import annotations

from typing import List, Tuple

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from xducraft_bot.shared import feature_gate

from .data_manager import get_show_offline_by_default
from .handlers import SUBCOMMAND_HANDLERS, handle_private_import, handle_query_all, handle_query_single

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_mc_status",
    description="Minecraft 服务器状态查询，支持多线服务器树、MOTD 彩色渲染与登录验证方式展示",
    usage="/mcs 查询状态 · /mcs help 查看完整帮助",
)

FEATURE_KEY = "mc_status"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="MC 服务器状态",
    description="/mcs 查询 Minecraft 服务器状态",
    # 指令驱动，不会主动发言，所以默认开启；管理员仍可按群关掉。
    default_enabled=True,
    passive=False,
))

mc_status = on_command("mcs", aliases={"mcstatus", "服务器", "状态"}, block=True, priority=4)


def split_query_options(arg_list: List[str]) -> Tuple[List[str], str]:
    """从查询参数中摘出最后一个 ``texture=<名称>``，保留其余位置参数。"""
    positional: List[str] = []
    texture_override = ""
    for argument in arg_list:
        key, separator, value = argument.partition("=")
        if separator and key.lower() == "texture":
            texture_override = value.strip()
        else:
            positional.append(argument)
    return positional, texture_override


@mc_status.handle()
async def handle_entry(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """按消息来源分发到私聊 / 群聊处理器。"""
    arg_list = args.extract_plain_text().strip().split()

    if isinstance(event, PrivateMessageEvent):
        if arg_list and arg_list[0].lower() == "import":
            await handle_private_import(bot, event, arg_list)
        await mc_status.finish(
            "私聊里只支持导入配置。\n请先在群里发送 /mcs edit 拿到编辑链接，改完再回来发送导入命令。"
        )

    if not isinstance(event, GroupMessageEvent):
        return

    # 功能隔离：没启用的群里一声不吭地退出，不做任何回复。
    if not feature_gate.is_enabled(FEATURE_KEY, event.group_id):
        return

    if not arg_list:
        await handle_query_all(bot, event, get_show_offline_by_default(event.group_id))

    # 管理子命令优先，避免 ``/mcs set ... texture=dirt`` 里的普通文本被当成查询选项。
    subcommand = arg_list[0].lower()
    if subcommand == "import":
        await mc_status.finish(
            "配置导入已移到私聊进行。\n请先在本群发送 /mcs edit，然后按私信里的提示操作。"
        )
    if subcommand in SUBCOMMAND_HANDLERS:
        await SUBCOMMAND_HANDLERS[subcommand](bot, event, arg_list)

    query_args, texture_override = split_query_options(arg_list)
    if not query_args:
        await handle_query_all(
            bot, event, get_show_offline_by_default(event.group_id), texture_override,
        )

    query_command = query_args[0].lower()
    if query_command == "all" and len(query_args) == 1:
        await handle_query_all(bot, event, True, texture_override)

    if len(query_args) == 1:
        await handle_query_single(bot, event, query_args[0], texture_override)

    await mc_status.finish(
        f"不认识的命令：{' '.join(query_args[:2])}\n发送 /mcs help 查看可用命令。"
    )
