
import ipaddress
import json
import random
import re
from urllib.parse import urlparse

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import Bot, MessageSegment, GroupMessageEvent
from nonebot.exception import MatcherException, FinishedException
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .data_manager import add_footer, clear_footer, add_server, remove_server, get_footer, get_server_list, \
    set_server_attribute, clear_server_attribute, get_server_info, import_group_data, export_group_data, get_show_offline_by_default
from .image_renderer import render_status_image
from .status_fetcher import get_single_server_status, get_all_servers_status, get_server_display_key
from .config_coder import compress_config, decompress_config
from .constants import WEB_UI_BASE_URL

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

usage_user="""命令：
/mcs : 查询群聊所有在线服务器状态
/mcs <IP> : 查询单个服务器状态
/mcs all : 查询所有已添加服务器状态
/mcs list : 查看已添加的服务器列表
/mcs help : 查看帮助信息"""

usage_admin="""【Web编辑器 (推荐)】
强烈推荐使用Web编辑器进行编辑
/mcs edit (export, editor): 生成配置链接并在Web UI中编辑
/mcs import <压缩字符串>: 从Web UI或备份中导入配置
---
【查询命令】
/mcs: 查询群聊所有在线服务器状态
/mcs <IP>: 查询单个服务器状态
/mcs all: 查询所有已添加服务器状态
/mcs list: 查看已添加的服务器列表
---
【快捷命令】
/mcs add <IP>: 添加服务器
/mcs remove <IP>: 移除服务器
---
【高级/调试命令】
/mcs set <IP> <attr> <value>: 设置服务器属性
/mcs clear <IP> <attr>: 清空/重置服务器属性
/mcs footer <文本>: 设置页脚文本
/mcs footer clear: 清除页脚文本
/mcs export_json: 导出原始JSON配置 (用于排查)
---
【帮助】
/mcs help: 查看本帮助信息"""

# 主命令
mc_status = on_command("mcs", aliases={"mcstatus", "服务器", "状态"}, block=True)


# --- 权限检查 ---

async def is_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    """检查用户是否是群管理员、群主或超级用户。"""
    # 检查是否是超级用户
    if await SUPERUSER(bot, event):
        return True
    # 检查是否是群管理员或群主
    if isinstance(event, GroupMessageEvent):
        return event.sender.role in ["admin", "owner"]
    return False


# --- 命令处理器 ---

async def _handle_add(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) < 2:
        await mc_status.finish("命令格式错误，请使用 /mcs add <IP>")
    ip = arg_list[1]
    if not is_valid_server_address(ip):
        await mc_status.finish(f"无效的服务器地址格式: {ip}")
    elif add_server(event.group_id, ip):
        await mc_status.finish(f"成功添加服务器: {ip}")
    else:
        await mc_status.finish(f"服务器 {ip} 已存在或添加失败")

async def _handle_remove(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) < 2:
        await mc_status.finish("命令格式错误，请使用 /mcs remove <IP>")
    ip = arg_list[1]
    if remove_server(event.group_id, ip):
        await mc_status.finish(f"成功移除服务器: {ip}")
    else:
        await mc_status.finish(f"服务器 {ip} 不存在或移除失败")

async def _handle_footer(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) > 1:
        if arg_list[1].lower() == "clear":
            clear_footer(event.group_id)
            await mc_status.finish("已清除页脚文本")
        else:
            footer_text = ' '.join(arg_list[1:])
            add_footer(event.group_id, footer_text)
            await mc_status.finish(f"已设置页脚: {footer_text}")
    else:
        current_footer = get_footer(event.group_id)
        if current_footer:
            await mc_status.finish(f"当前页脚: {current_footer}")
        else:
            await mc_status.finish("尚未设置页脚文本")

async def _handle_set(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) < 4:
        await mc_status.finish("命令格式错误，请使用 /mcs set <IP> <attr> <value>")

    ip = arg_list[1]
    attribute = arg_list[2].lower()
    value = ' '.join(arg_list[3:]) # 允许值带有空格

    valid_attributes = {"tag", "tag_color", "comment", "priority", "ignore_in_list"}
    if attribute not in valid_attributes:
        if attribute == "parent_ip":
            await mc_status.finish(f"不支持直接修改 parent_ip。\n请使用 /mcs edit 命令打开Web UI，通过拖拽来修改服务器层级关系。")
        await mc_status.finish(f"不支持设置属性: {attribute}。请从 {', '.join(valid_attributes)} 中选择。")

    if attribute == "priority":
        try:
            value = int(value)
        except ValueError:
            await mc_status.finish("优先级 (priority) 必须是一个整数。")
    elif attribute == "ignore_in_list":
        if value.lower() in ['true', '1', 'yes', 'y', '是']:
            value = True
        elif value.lower() in ['false', '0', 'no', 'n', '否']:
            value = False
        else:
            await mc_status.finish("隐藏属性 (ignore_in_list) 的值必须是 True/False。")
    elif attribute == "tag_color":
        if value.startswith("#"):
            value = value[1:]
        if not is_valid_hex_color(value):
            await mc_status.finish("颜色值无效。请使用标准的6位十六进制代码 (例如: FF00AA)。")
        value = value.upper()

    if set_server_attribute(event.group_id, ip, attribute, value):
        await mc_status.finish(f"服务器 {ip} 的属性 [{attribute}] 已成功设置为: {value}")
    else:
        await mc_status.finish(f"设置失败: 服务器 {ip} 不存在。")

async def _handle_clear(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) != 3:
        await mc_status.finish("命令格式错误，请使用 /mcs clear <IP> <attribute>")

    ip = arg_list[1]
    attribute = arg_list[2].lower()
    valid_attributes = {"tag", "tag_color", "parent_ip", "priority"}

    if attribute in valid_attributes:
        if clear_server_attribute(event.group_id, ip, attribute):
            await mc_status.finish(f"服务器 {ip} 的属性 [{attribute}] 已成功清空/重置。")
        else:
            await mc_status.finish(f"清空失败: 服务器 {ip} 不存在。")
    else:
        await mc_status.finish(f"不支持清空属性: {attribute}。请从 {', '.join(valid_attributes)} 中选择。")

async def _handle_list(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if len(arg_list) == 1:
        await handle_list_simple(bot, event)
    else:
        await mc_status.finish("未知参数，请使用 /mcs list 查看服务器列表。")


async def _handle_export(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    group_data = export_group_data(event.group_id)
    if not group_data or not group_data.get("servers"):
        await mc_status.finish("当前群聊没有可导出的服务器配置。")
        
    compressed_str = compress_config(group_data)
    if not compressed_str:
        await mc_status.finish("导出失败：压缩配置时发生错误。")

    export_url = f"{WEB_UI_BASE_URL}?data={compressed_str}"
    
    nodes = [
        {"type": "node", "data": {"name": "配置导出", "uin": event.self_id, "content": "配置导出成功！请点击链接导入到Web UI："}},
        {"type": "node", "data": {"name": "Web UI链接", "uin": event.self_id, "content": export_url}}
    ]
    try:
        await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
    except Exception:
        await mc_status.finish(f"配置导出成功！\n请点击链接导入到Web UI：\n{export_url}")
    else:
        await mc_status.finish()


async def _handle_export_json(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    group_data = export_group_data(event.group_id)
    if not group_data or not group_data.get("servers"):
        await mc_status.finish("当前群聊没有可导出的服务器配置。")
    try:
        json_str = json.dumps(group_data, indent=2, ensure_ascii=False)
    except Exception as e:
        await mc_status.finish(f"生成JSON时发生错误：{e}")
    
    nodes = [
        {"type": "node", "data": {"name": "JSON导出", "uin": event.self_id, "content": f"当前群聊的原始JSON配置如下：\n您可以复制此JSON内容，手动导入到Web编辑器：{WEB_UI_BASE_URL}"}},
        {"type": "node", "data": {"name": "JSON内容", "uin": event.self_id, "content": json_str}}
    ]
    try:
        await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
    except Exception:
        await mc_status.finish(f"当前群聊的原始JSON配置如下：\n您可以复制此JSON内容，手动导入到Web编辑器：{WEB_UI_BASE_URL}\n{json_str}")
    else:
        await mc_status.finish()

async def _handle_import(bot: Bot, event: GroupMessageEvent, arg_list: list):
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) < 2:
        await mc_status.finish("导入命令格式错误，请使用 /mcs import <压缩字符串>")
    compressed_str = arg_list[1]
    decompressed_data = decompress_config(compressed_str)
    if decompressed_data is None:
        await mc_status.finish("导入失败：无法解压或解析该字符串，请检查输入是否正确。")
        return
    if import_group_data(event.group_id, decompressed_data):
        await mc_status.finish("成功导入配置！已覆盖本群聊的原有服务器设置。")
    else:
        await mc_status.finish("导入失败：数据结构不符合要求。")

async def _handle_help(bot: Bot, event: GroupMessageEvent, arg_list: list):
    is_su_or_admin = await is_admin(bot, event)
    # 对于普通用户
    if not is_su_or_admin:
        nodes = [{"type": "node", "data": {"name": "帮助", "uin": event.self_id, "content": usage_user}}]
        try:
            await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
        except Exception:
            await mc_status.finish(usage_user) # 回退
        else:
            await mc_status.finish()
        return

    # 对于管理员
    try:
        raw_sections = usage_admin.split('---\n')
        nodes = []
        for section_content in raw_sections:
            section_content = section_content.strip()
            if not section_content:
                continue

            node = {"type": "node", "data": {"name": "管理员帮助", "uin": event.self_id, "content": section_content}}
            nodes.append(node)
        
        await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
    except Exception:
        await mc_status.finish(usage_admin)
    else:
        await mc_status.finish()


SUBCOMMAND_HANDLERS = {
    "add": _handle_add,
    "remove": _handle_remove,
    "footer": _handle_footer,
    "set": _handle_set,
    "clear": _handle_clear,
    "list": _handle_list,
    "export": _handle_export,
    "edit": _handle_export,
    "editor": _handle_export,
    "export_json": _handle_export_json,
    "import": _handle_import,
    "help": _handle_help,
}

@mc_status.handle()
async def handle_main_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    arg_list = arg_text.split()

    if not arg_list:
        show_all = get_show_offline_by_default(event.group_id)
        await handle_query_all(bot, event, show_all)
        return

    subcommand = arg_list[0].lower()

    if subcommand in SUBCOMMAND_HANDLERS:
        if subcommand == 'import' and len(arg_text.split(maxsplit=1)) > 1:
            handler_args = ['import', arg_text.split(maxsplit=1)[1]]
        else:
            handler_args = arg_list
        await SUBCOMMAND_HANDLERS[subcommand](bot, event, handler_args)
    elif subcommand == "all" and len(arg_list) == 1:
        await handle_query_all(bot, event, True)
    elif len(arg_list) == 1:
        await handle_query_single(bot, event, arg_list[0])
    else:
        await mc_status.finish("未知命令，使用 /mcs help 查看帮助")


async def handle_query_all(bot: Bot, event: GroupMessageEvent,show_all_servers: bool):
    """查询所有服务器状态"""
    try:
        servers = get_server_list(event.group_id)
        if not servers:
            await mc_status.finish("本群尚未添加Minecraft服务器")

        await mc_status.send("正在查询所有服务器状态...")
        server_data_list = await get_all_servers_status(event.group_id)
        image_path = await render_status_image(server_data_list, event.group_id, show_all_servers)
        reply_message = MessageSegment.image(file=f"file:///{image_path}")
    except FinishedException:
        raise
    except Exception as e:
        reply_message = f"查询所有服务器状态失败: {e}"
        raise
    await mc_status.finish(reply_message)


async def handle_query_single(bot: Bot, event: GroupMessageEvent, ip: str):
    """查询单个服务器状态"""
    if not is_valid_server_address(ip):
        # --- 特殊彩蛋区 ---
        if '❤' in ip: await mc_status.finish("❤服务器？这怕不是运行在我的心巴上！")
        if ip == '127.0.0.1' or ip.lower() == 'localhost': await mc_status.finish(random.choice(["...", "..."]))
        # ... etc
        await mc_status.finish(random.choice(["...", "..."]))

    try:
        await mc_status.send(f"正在查询服务器 {ip} 的状态...")
        server_data = await get_single_server_status(ip)
        image_path = await render_status_image([server_data], event.group_id,True)
        reply_message = MessageSegment.image(file=f"file:///{image_path}")
    except FinishedException:
        raise
    except Exception as e:
        reply_message = f"查询 {ip} 失败: {e}"
    await mc_status.finish(reply_message)



async def handle_list_simple(bot: Bot, event: GroupMessageEvent):
    """处理 /mcs list 命令，递归显示树形服务器列表"""
    server_tree = get_server_list(event.group_id)

    if not server_tree:
        await mc_status.finish("尚未添加任何服务器")
        return

    def _format_tree(nodes: list, level=0) -> list[str]:
        lines = []
        for i, s in enumerate(nodes):
            ip = s.get('ip', '未知服务器')
            tag = s.get('tag', '')
            comment = s.get('comment', '')
            
            prefix = f"[{tag}] " if tag else ""
            display_name = f"{comment} ({ip})" if comment else ip
            
            indent = "  " * level
            connector = "↳ " if level > 0 else ""
            
            lines.append(f"{indent}{connector}{prefix}{display_name}")
            
            if s.get('children'):
                lines.extend(_format_tree(s['children'], level + 1))
        return lines

    server_list_str = "\n".join(_format_tree(server_tree))
    
    try:
        await bot.send_group_forward_msg(group_id=event.group_id, messages=[
            {"type": "node", "data": {"name": "服务器列表", "uin": event.self_id, "content": f"已添加的服务器:\n{server_list_str}"}}
        ])
    except Exception:
        await mc_status.finish(f"已添加的服务器:\n{server_list_str}")
    else:
        await mc_status.finish()


# 屏蔽危险网站
BLACKLISTED_PATTERNS = [
    'gov.cn',
    'mil.cn',
]


def is_valid_server_address(address: str) -> bool:
    """
    强化版的服务器地址验证函数。
    支持：域名、IPv4、IPv6 及其带端口的格式。
    """
    if not isinstance(address, str):
        return False

    address = address.strip()

    if not address or ' ' in address:
        return False

    try:
        parsed = urlparse('//' + address)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False

    if host is None:
        return False

    if port is not None:
        if not (1 <= port <= 65535):
            return False

    host_lower = host.lower()
    for pattern in BLACKLISTED_PATTERNS:
        pattern_cleaned = pattern.lstrip('.')
        if host_lower == pattern_cleaned or host_lower.endswith('.' + pattern_cleaned):
            return False

    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    try:
        host_idna = host.encode('idna').decode('ascii')
    except UnicodeError:
        return False

    if len(host_idna) > 253 or host_idna.startswith('-') or host_idna.endswith('-') or \
            host_idna.startswith('.') or host_idna.endswith('.') or '..' in host_idna:
        return False

    labels = host_idna.split('.')
    if not labels or any(len(label) > 63 or not label for label in labels):
        return False

    if host_lower == 'localhost':
        return True

    if '.' not in host_idna:
        return False

    return True


def is_valid_hex_color(color_str: str) -> bool:
    """
    检查字符串是否是有效的6位十六进制颜色代码（不区分大小写）。
    """
    return bool(re.fullmatch(r'^[0-9a-fA-F]{6}$', color_str.strip()))
