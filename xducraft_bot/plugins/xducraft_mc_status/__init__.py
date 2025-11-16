from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.internal.adapter import Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata


# 从 handlers 导入子命令处理逻辑
from .handlers import SUBCOMMAND_HANDLERS, handle_query_all, handle_query_single

# 从 data_manager 导入需要在主命令中直接使用的函数
from .data_manager import get_show_offline_by_default

mc_status = on_command("mcs", aliases={"mcstatus", "服务器", "状态"}, block=True)

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_mc_status",
    description="为XDUCraft提供服务器状态查询功能",
    usage="""【用户命令】
/mcs: 查询服务器状态
/mcs <IP>: 查询单个服务器
/mcs all: 查询所有服务器
/mcs list: 查看服务器列表

【管理员命令】
/mcs edit: 获取配置链接以在Web UI中编辑
/mcs import <压缩字符串>: 从Web UI或备份中导入配置
/mcs add <IP>: 快速添加服务器
/mcs remove <IP>: 快速移除服务器
...更多命令请使用 /mcs help 查看""",
)


# 主命令处理
@mc_status.handle()
async def handle_main_command(
    bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()
):
    """
    主命令分发器
    """
    arg_text = args.extract_plain_text().strip()
    arg_list = arg_text.split()

    # --- 命令分发逻辑 ---
    if not arg_list:
        show_all = get_show_offline_by_default(event.group_id)
        await handle_query_all(bot, event, show_all)
        return

    subcommand = arg_list[0].lower()

    if subcommand in SUBCOMMAND_HANDLERS:
        handler_args = arg_list
        # 调用在 handlers.py 中定义的子命令处理器
        await SUBCOMMAND_HANDLERS[subcommand](bot, event, handler_args)
    elif subcommand == "all" and len(arg_list) == 1:
        await handle_query_all(bot, event, True)
    elif len(arg_list) == 1:
        # 如果不是任何已知的子命令，则视为查询单个服务器
        await handle_query_single(bot, event, arg_list[0])
    else:
        # 未知命令格式
        await mc_status.finish("未知命令，使用 /mcs help 查看帮助")
