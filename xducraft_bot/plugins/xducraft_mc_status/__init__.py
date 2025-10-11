import json
import re

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import MessageSegment, GroupMessageEvent
from nonebot.exception import MatcherException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .data_manager import add_footer, clear_footer, add_server, remove_server, get_footer, get_server_list, \
    set_server_attribute, clear_server_attribute, get_server_info
from .image_renderer import render_status_image
from .status_fetcher import get_single_server_status, get_all_servers_status, get_server_display_key

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_mc_status",
    description="为XDUCraft提供服务器状态查询功能",
    usage="""命令：
/mcs : 查询群聊所有在线服务器状态
/mcs <IP> : 查询单个服务器状态
/mcs all : 查询所有已添加服务器状态
/mcs add <IP> : 添加服务器
/mcs remove <IP> : 移除服务器
/mcs set <IP> <attr> <value> : 设置服务器属性（tag, tag_color, server_type, parent_ip, priority）
/mcs clear <IP> <attr> : 清空/重置服务器属性（tag, tag_color, parent_ip, priority）
/mcs footer <文本> : 设置页脚文本
/mcs footer clear : 清除页脚文本
/mcs list : 查看已添加的服务器列表
/mcs list detail : 管理员查看所有服务器的关键配置（优先级、标签、类型等）
/mcs list detail <IP> : 管理员查看单个服务器的所有完整属性（包括隐藏属性）
/mcs help : 查看帮助信息""",
)

usage_user="""命令：
/mcs : 查询群聊所有在线服务器状态
/mcs <IP> : 查询单个服务器状态
/mcs all : 查询所有已添加服务器状态
/mcs list : 查看已添加的服务器列表
/mcs help : 查看帮助信息"""

usage_admin="""命令：
/mcs : 查询群聊所有在线服务器状态
/mcs <IP> : 查询单个服务器状态
/mcs all : 查询所有已添加服务器状态
/mcs add <IP> : 添加服务器
/mcs remove <IP> : 移除服务器
/mcs set <IP> <attr> <value> : 设置服务器属性（tag, tag_color, server_type, parent_ip, priority）
/mcs clear <IP> <attr> : 清空/重置服务器属性（tag, tag_color, parent_ip, priority）
/mcs footer <文本> : 设置页脚文本
/mcs footer clear : 清除页脚文本
/mcs list : 查看已添加的服务器列表
/mcs list detail : 管理员查看所有服务器的关键配置（优先级、标签、类型等）
/mcs list detail <IP> : 管理员查看单个服务器的所有完整属性（包括隐藏属性）
/mcs help : 查看帮助信息"""

# 主命令
mc_status = on_command("mcs", aliases={"mcstatus", "服务器", "状态"}, block=True)


@mc_status.handle()
async def handle_main_command(event: GroupMessageEvent, args: Message = CommandArg()):
    # 解析参数
    arg_list = args.extract_plain_text().strip().split()

    if not arg_list:
        # 没有参数：查询所有服务器状态
        await handle_query_all(event,False)
    elif len(arg_list) == 1 and arg_list[0] == "all":
        await handle_query_all(event,True)
    elif len(arg_list) == 1 and not arg_list[0].startswith(('add', 'remove', 'footer', 'list', 'help')):
        # 单个参数且不是子命令：查询指定服务器
        await handle_query_single(event, arg_list[0])
    else:
        # 处理子命令
        await handle_subcommands(event, arg_list)


async def handle_query_all(event: GroupMessageEvent,show_all_servers: bool):
    """查询所有服务器状态"""
    try:
        servers = get_server_list(event.group_id)
        # 未添加服务器
        if not servers:
            await mc_status.finish("本群尚未添加Minecraft服务器")

        await mc_status.send("正在查询所有服务器状态...")
        server_data_list = await get_all_servers_status(event.group_id)
        image_path = await render_status_image(server_data_list, event.group_id, show_all_servers)
        reply_message = MessageSegment.image(file=f"file:///{image_path}")
        # print(server_data_list)
    except MatcherException:
        raise
    except Exception as e:
        # reply_message = f"查询所有服务器状态失败: {e}"
        raise
    await mc_status.finish(reply_message)


async def handle_query_single(event: GroupMessageEvent, ip: str):
    """查询单个服务器状态"""
    try:
        await mc_status.send(f"正在查询服务器 {ip} 的状态...")
        server_data = await get_single_server_status(ip)
        image_path = await render_status_image([server_data], event.group_id,True)
        reply_message = MessageSegment.image(file=f"file:///{image_path}")
    except Exception as e:
        reply_message = f"查询 {ip} 失败: {e}"
    await mc_status.finish(reply_message)


async def handle_subcommands(event: GroupMessageEvent, arg_list: list):
    """处理子命令"""
    subcommand = arg_list[0].lower()

    if subcommand == "add" and len(arg_list) > 1:
        # 添加服务器: /mcs add <IP>
        ip = arg_list[1]
        if not is_admin(event):
            await mc_status.finish(f"你没有执行该命令的权限")
        elif not is_valid_server_address(ip):
            await mc_status.finish(f"无效的服务器地址格式: {ip}")
        elif add_server(event.group_id, ip):
            await mc_status.finish(f"成功添加服务器: {ip}")
        else:
            await mc_status.finish(f"服务器 {ip} 已存在或添加失败")

    elif subcommand == "remove" and len(arg_list) > 1:
        # 移除服务器: /mcs remove <IP>
        ip = arg_list[1]
        if not is_admin(event):
            await mc_status.finish(f"你没有执行该命令的权限")
        elif remove_server(event.group_id, ip):
            await mc_status.finish(f"成功移除服务器: {ip}")
        else:
            await mc_status.finish(f"服务器 {ip} 不存在或移除失败")

    elif subcommand == "footer":
        if not is_admin(event):
            await mc_status.finish(f"你没有执行该命令的权限")
        elif len(arg_list) > 1:
            if arg_list[1].lower() == "clear":
                # 清除页脚: /mcs footer clear
                clear_footer(event.group_id)
                await mc_status.finish("已清除页脚文本")
            else:
                # 设置页脚: /mcs footer <文本>
                footer_text = ' '.join(arg_list[1:])
                add_footer(event.group_id, footer_text)
                await mc_status.finish(f"已设置页脚: {footer_text}")
        else:
            # 查看当前页脚: /mcs footer
            current_footer = get_footer(event.group_id)
            if current_footer:
                await mc_status.finish(f"当前页脚: {current_footer}")
            else:
                await mc_status.finish("尚未设置页脚文本")

    elif subcommand == "set" and len(arg_list) >= 4:
        if not is_admin(event):
            await mc_status.finish("你没有执行该命令的权限")

        # 格式: /mcs set <IP> <attribute> <value>
        ip = arg_list[1]
        attribute = arg_list[2].lower()
        value = arg_list[3]

        # 允许设置的属性白名单 (防止用户设置不存在或不应被设置的属性)
        valid_attributes = {
            "tag": str, "tag_color": str, "server_type": str,
            "parent_ip": str, "priority": int
        }

        if attribute not in valid_attributes:
            await mc_status.finish(
                f"不支持设置属性: {attribute}。请使用 tag, tag_color, server_type, parent_ip, 或 priority。")

        # 针对 'priority' 进行特殊类型转换
        if attribute == "priority":
            try:
                value = int(value)
            except ValueError:
                await mc_status.finish("优先级 (priority) 必须是一个整数。")

        # 针对 'server_type' 进行值校验 (可选，但推荐)
        if attribute == "server_type" and value.lower() not in ['standalone', 'parent', 'child']:
            await mc_status.finish("服务器类型 (server_type) 必须是 standalone, parent, 或 child。")

        # 针对 'tag_color' 进行规范化和值验证
        if attribute == "tag_color":
            # 1. 规范化：去除 # 并转换为大写，确保一致性
            if value.startswith("#"):
                value = value[1:]

            # 2. 验证：必须是6位十六进制数
            if not is_valid_hex_color(value):
                await mc_status.finish("颜色值无效。请使用标准的6位十六进制代码 (例如: FF00AA 或 #FF00AA)。")

            # 3. 规范化：转换为大写，方便后续PIL处理
            value = value.upper()

        if set_server_attribute(event.group_id, ip, attribute, value):
            await mc_status.finish(f"服务器 {ip} 的属性 [{attribute}] 已成功设置为: {value}")
        else:
            await mc_status.finish(f"设置失败: 服务器 {ip} 不存在。")

        # --- 新增：清空服务器属性命令 /mcs clear ---
    elif subcommand == "clear" and len(arg_list) == 3:
        if not is_admin(event):
            await mc_status.finish("你没有执行该命令的权限")

        # 格式: /mcs clear <IP> <attribute>
        ip = arg_list[1]
        attribute = arg_list[2].lower()

        if attribute in ["tag", "tag_color", "parent_ip", "priority"]:
            if clear_server_attribute(event.group_id, ip, attribute):
                await mc_status.finish(f"服务器 {ip} 的属性 [{attribute}] 已成功清空/重置。")
            else:
                await mc_status.finish(f"清空失败: 服务器 {ip} 不存在。")
        else:
            await mc_status.finish(f"不支持清空属性: {attribute}。请使用 tag, tag_color, parent_ip, 或 priority。")


    elif subcommand == "list":
        # 现有 /mcs list 逻辑：只显示简要信息，过滤隐藏服务器
        if len(arg_list) == 1:
            await handle_list_simple(event)  # 重构现有逻辑为独立函数，保持清晰

        # 新增 /mcs list detail 逻辑
        elif arg_list[1].lower() == "detail":
            if not is_admin(event):
                await mc_status.finish("你没有执行该命令的权限")

            if len(arg_list) == 2:
                # /mcs list detail：显示所有服务器的关键属性
                await handle_list_detail_all(event)
            elif len(arg_list) == 3:
                # /mcs list detail <IP>：显示单个服务器的所有属性
                ip_to_show = arg_list[2]
                await handle_list_detail_single(event, ip_to_show)
            else:
                await mc_status.finish("命令格式错误，请使用 /mcs list detail 或 /mcs list detail <IP>")


    elif subcommand == "help":
        # 显示帮助: /mcs help
        help_text = usage_admin if is_admin(event) else usage_user
        await mc_status.finish(help_text)

    else:
        # 未知子命令
        await mc_status.finish("未知命令，使用 /mcs help 查看帮助")


async def handle_list_simple(event: GroupMessageEvent):
    """处理 /mcs list 命令，显示简要服务器列表"""
    servers = get_server_list(event.group_id)

    if servers:
        # --- 关键修改 1: 过滤掉标记为忽略的服务器 ---
        display_servers = [
            s for s in servers
            if not s.get('ignore_in_list')
        ]

        if not display_servers:
            await mc_status.finish("已添加服务器，但所有服务器均已设置为在列表中隐藏。")
            return

        # 2. 对用于显示的列表进行排序
        # 使用 display_servers 而非原始 servers
        sorted_servers = sorted(display_servers, key=get_server_display_key)

        # 3. 格式化输出
        server_lines = []

        # 这里的 i 是在显示列表中的索引，从 0 开始
        for i, s in enumerate(sorted_servers):
            ip = s.get('ip', '未知服务器')
            tag = s.get('tag', '')
            prefix = f"[{tag}] " if tag else ""

            # 显示主从关系
            server_type = s.get('server_type', 'standalone')
            indent = "  ↳ " if server_type == 'child' else ""

            # i + 1 是服务器的序号
            server_lines.append(f"{i + 1}. {indent}{prefix}{ip}")

        server_list = "\n".join(server_lines)
        await mc_status.finish(f"已添加的服务器:\n{server_list}")
    else:
        await mc_status.finish("尚未添加任何服务器")


async def handle_list_detail_all(event: GroupMessageEvent):
    """处理 /mcs list detail 命令，显示所有服务器的关键属性"""
    servers = get_server_list(event.group_id)
    if not servers:
        await mc_status.finish("本群尚未添加Minecraft服务器")

    sorted_servers = sorted(servers, key=get_server_display_key)

    output_lines = ["--- 服务器完整配置概览 ---"]
    for i, s in enumerate(sorted_servers):
        # 格式化关键属性
        tag_color = s.get('tag_color', 'N/A')
        parent_ip = s.get('parent_ip', 'N/A')
        ignore = "是" if s.get('ignore_in_list') else "否"

        line = (
            f"[{s.get('priority', 100)}] {s['ip']}\n"
            f"  Tag: {s.get('tag', '无')} (Color: {tag_color})\n"
            f"  Type: {s.get('server_type', 'standalone')} (Parent: {parent_ip})\n"
            f"  隐藏: {ignore}"
        )
        output_lines.append(line)
        output_lines.append("-" * 20)

    await mc_status.finish("\n".join(output_lines))


async def handle_list_detail_single(event: GroupMessageEvent, ip: str):
    """处理 /mcs list detail <IP> 命令，显示单个服务器的所有属性"""
    # 假设 data_manager 中有 get_server_info 函数，能返回单个服务器的完整字典
    server_info = get_server_info(event.group_id, ip)

    if not server_info:
        await mc_status.finish(f"未找到服务器: {ip}")
        return

    output_lines = [f"--- 服务器 {ip} 完整属性 ---"]

    # 使用 JSON 格式化输出，清晰显示所有键值对，包括隐藏属性
    formatted_json = json.dumps(server_info, indent=2, ensure_ascii=False)
    output_lines.append(formatted_json)

    # 提示如何修改
    output_lines.append("\n使用 /mcs set <IP> <attr> <value> 进行修改。")

    await mc_status.finish("\n".join(output_lines))


def is_valid_server_address(address: str) -> bool:
    """
    验证服务器地址格式
    """
    # 检查是否包含空格（IP地址不应该有空格）
    if ' ' in address:
        return False

    # 简单的格式检查
    if ':' in address:
        # 包含端口的格式：address:port
        parts = address.split(':')
        if len(parts) != 2:
            return False
        try:
            port = int(parts[1])
            return 1 <= port <= 65535
        except ValueError:
            return False

    # 不含端口的格式（使用默认端口）
    return True


def is_valid_hex_color(color_str: str) -> bool:
    """
    检查字符串是否是有效的6位十六进制颜色代码（不区分大小写）。
    """
    # 允许 3 位（RGB）或 6 位（RRGGBB）格式，但 6 位更常见和推荐
    # 这里只检查 6 位格式，因为它是 PIL 的标准输入格式
    return bool(re.fullmatch(r'^[0-9a-fA-F]{6}$', color_str.strip()))


def is_admin(event: GroupMessageEvent):
    return event.sender.role in ["admin", "owner"]
