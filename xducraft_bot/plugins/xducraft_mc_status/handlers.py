import json
import random
import re

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment, PrivateMessageEvent
from nonebot.exception import MatcherException


# Dictionary to track users who are in the process of editing a group's config
#
# Stores a mapping from a user_id to the group_id they are editing.
# This allows the bot to know which group's data to update when it receives an
# import command in a private message from that user.
EDITING_USERS = {}


from .config_coder import compress_config, decompress_config
from .constants import WEB_UI_BASE_URL, USAGE_USER, USAGE_ADMIN
from .data_manager import add_server, remove_server, clear_footer, add_footer, get_footer, set_server_attribute, \
    clear_server_attribute, export_group_data, import_group_data, get_server_list, get_server_info
from .image_renderer import render_status_image
from .status_fetcher import get_all_servers_status, get_single_server_status
from .utils import is_admin, is_valid_server_address, is_valid_hex_color


async def _handle_add(bot: Bot, event: GroupMessageEvent, arg_list: list):
    from . import mc_status
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
    from . import mc_status
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
    from . import mc_status
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
    from . import mc_status
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) < 4:
        await mc_status.finish("命令格式错误，请使用 /mcs set <IP> <attr> <value>")

    ip = arg_list[1]
    attribute = arg_list[2].lower()
    value = ' '.join(arg_list[3:]) # 允许值带有空格

    valid_attributes = {"tag", "tag_color", "comment", "priority", "ignore_in_list", "hide_ip", "display_name"}
    if attribute not in valid_attributes:
        if attribute == "parent_ip":
            await mc_status.finish(f"不支持直接修改 parent_ip。\n请使用 /mcs edit 命令打开Web UI，通过拖拽来修改服务器层级关系。")
        await mc_status.finish(f"不支持设置属性: {attribute}。请从 {', '.join(valid_attributes)} 中选择。")

    if attribute == "priority":
        try:
            value = int(value)
        except ValueError:
            await mc_status.finish("优先级 (priority) 必须是一个整数。")
    elif attribute in ["ignore_in_list", "hide_ip"]:
        if value.lower() in ['true', '1', 'yes', 'y', '是']:
            value = True
        elif value.lower() in ['false', '0', 'no', 'n', '否']:
            value = False
        else:
            await mc_status.finish(f"属性 [{attribute}] 的值必须是 True/False。")
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
    from . import mc_status
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")
    if len(arg_list) != 3:
        await mc_status.finish("命令格式错误，请使用 /mcs clear <IP> <attribute>")

    ip = arg_list[1]
    attribute = arg_list[2].lower()
    valid_attributes = {"tag", "tag_color", "parent_ip", "priority", "comment", "ignore_in_list", "hide_ip", "display_name"}

    if attribute in valid_attributes:
        if clear_server_attribute(event.group_id, ip, attribute):
            await mc_status.finish(f"服务器 {ip} 的属性 [{attribute}] 已成功清空/重置。")
        else:
            await mc_status.finish(f"清空失败: 服务器 {ip} 不存在。")
    else:
        await mc_status.finish(f"不支持清空属性: {attribute}。请从 {', '.join(valid_attributes)} 中选择。")


async def _handle_list(bot: Bot, event: GroupMessageEvent, arg_list: list):
    from . import mc_status
    if len(arg_list) == 1:
        await handle_list_simple(bot, event)
    else:
        await mc_status.finish("未知参数，请使用 /mcs list 查看服务器列表。")


async def _handle_edit(bot: Bot, event: GroupMessageEvent, arg_list: list):
    from . import mc_status
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")

    user_id = event.user_id
    group_id = event.group_id

    group_data = export_group_data(group_id) or {}
    compressed_str = compress_config(group_data)
    if not compressed_str:
        await mc_status.finish("导出失败：压缩配置时发生错误。")

    export_url = f"{WEB_UI_BASE_URL}?data={compressed_str}"

    # Store the user's state
    EDITING_USERS[user_id] = group_id
    
    try:
        # Use send_forward_msg for private chat
        messages = [
            {
                "type": "node",
                "data": {
                    "name": "配置小助手",
                    "uin": event.self_id,
                    "content": (
                        "请点击以下链接，在Web UI中编辑服务器配置：\n"
                        f"{export_url}\n\n"
                        "编辑完成后，请复制页面底部的【导出配置】中的压缩字符串。"
                    )
                }
            },
            {
                "type": "node",
                "data": {
                    "name": "配置小助手",
                    "uin": event.self_id,
                    "content": "然后在此私聊窗口中通过以下命令导入：\n/mcs import <压缩字符串>"
                }
            }
        ]
        await bot.call_api('send_private_forward_msg', user_id=user_id, messages=messages)

    except Exception as e:
        # Clean up state if private message fails
        if user_id in EDITING_USERS:
            del EDITING_USERS[user_id]
        await mc_status.finish(f"向您发送私信失败，请检查是否已添加机器人为好友或是否开启了临时会话权限。错误: {e}")

    await mc_status.finish("我已经通过私信将配置链接发送给你，请注意查收。")


async def _handle_export_json(bot: Bot, event: GroupMessageEvent, arg_list: list):
    from . import mc_status
    if not await is_admin(bot, event):
        await mc_status.finish("你没有执行该命令的权限")

    group_data = export_group_data(event.group_id) or {}
    try:
        json_str = json.dumps(group_data, indent=2, ensure_ascii=False)
        messages = [
            {
                "type": "node",
                "data": {
                    "name": "JSON导出",
                    "uin": event.self_id,
                    "content": f"当前群聊的原始JSON配置如下：\n{json_str}"
                }
            }
        ]
        await bot.call_api('send_private_forward_msg', user_id=event.user_id, messages=messages)

    except Exception as e:
        await mc_status.finish(f"发送JSON配置失败：{e}")

    await mc_status.finish("我已通过私信将JSON配置发送给你。")


async def handle_private_import(bot: Bot, event: PrivateMessageEvent, arg_list: list):
    from . import mc_status
    user_id = event.user_id
    if user_id not in EDITING_USERS:
        await mc_status.finish("无效的导入操作。请先在需要编辑的群聊中使用 /mcs edit 命令。")

    if not arg_list or arg_list[0].lower() != 'import' or len(arg_list) != 2:
        await mc_status.finish("私聊导入命令格式错误，请使用 /mcs import <压缩字符串>")

    compressed_str = arg_list[1]
    group_id = EDITING_USERS[user_id]

    decompressed_data = decompress_config(compressed_str)
    if decompressed_data is None:
        await mc_status.finish("导入失败：无法解压或解析该字符串，请检查输入是否正确。")

    if import_group_data(group_id, decompressed_data):
        group_name = str(group_id)
        try:
            group_info = await bot.get_group_info(group_id=group_id)
            group_name = group_info.get('group_name', group_name)
        except Exception:
            pass  # Bot might not be in group anymore, proceed with default group_id

        del EDITING_USERS[user_id]  # Clear state after successful import
        await mc_status.finish(f"群聊 [{group_name}] 的配置导入成功！")

        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=f"本群的服务器配置已由用户 {event.sender.nickname} 更新。"
            )
        except Exception:
            # Ignore if sending to group fails (e.g., bot kicked)
            pass
    else:
        await mc_status.finish("导入失败：数据结构不符合要求。")


async def _handle_help(bot: Bot, event: GroupMessageEvent, arg_list: list):
    from . import mc_status
    is_su_or_admin = await is_admin(bot, event)
    # 对于普通用户
    if not is_su_or_admin:
        nodes = [{"type": "node", "data": {"name": "帮助", "uin": event.self_id, "content": USAGE_USER}}]
        try:
            await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
        except Exception:
            await mc_status.finish(USAGE_USER) # 回退
        else:
            await mc_status.finish()
        return

    # 对于管理员
    try:
        raw_sections = USAGE_ADMIN.split('---\n')
        nodes = []
        for section_content in raw_sections:
            section_content = section_content.strip()
            if not section_content:
                continue

            node = {"type": "node", "data": {"name": "管理员帮助", "uin": event.self_id, "content": section_content}}
            nodes.append(node)

        await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
    except Exception:
        await mc_status.finish(USAGE_ADMIN)
    else:
        await mc_status.finish()


async def handle_query_all(bot: Bot, event: GroupMessageEvent,show_all_servers: bool):
    from . import mc_status
    """查询所有服务器状态"""
    try:
        servers = get_server_list(event.group_id)
        if not servers:
            await mc_status.finish("本群尚未添加Minecraft服务器")

        await mc_status.send("正在查询所有服务器状态...")
        server_data_list = await get_all_servers_status(event.group_id)
        image_path = await render_status_image(server_data_list, event.group_id, show_all_servers)
        reply_message = MessageSegment.image(file=f"file:///{image_path}")
    except MatcherException:
        raise
    except Exception as e:
        reply_message = f"查询所有服务器状态失败: {e}"
        # raise
    await mc_status.finish(reply_message)


async def handle_query_single(bot: Bot, event: GroupMessageEvent, ip: str):
    from . import mc_status
    """查询单个服务器状态"""
    if not is_valid_server_address(ip):
        # 假设 ip 是用户输入, is_valid_server_address(ip) 已返回 False

        # --- 1. 特殊彩蛋区 (优先级最高) ---
        if '❤' in ip:
            await mc_status.finish("❤服务器？这怕不是运行在我的心巴上！")

        if ip == '127.0.0.1' or ip.lower() == 'localhost':
            responses = [
                "你搁这儿开单机呢？查询127.0.0.1...找到了！在你电脑里！",
                "查询 `localhost`... 数据库连接成功！...等等，我为什么要查我自己？Σ( ° △ °|||)",
            ]
            await mc_status.finish(random.choice(responses))

        if ip == '192.168.1.1' or ip == '192.168.0.1':
            await mc_status.finish("你查路由器干嘛！是不是想改WiFi密码不让我上了！(°òДó)ﾉ")

        if '114514' in ip:
            await mc_status.finish(f"查询 {ip} 中...哼哼啊啊啊啊啊啊（查询失败）")

        if ip == '404':
            await mc_status.finish("Server Not Found. (你看，404自己都说找不到了)")

        # --- 2. 格式分类区 ---

        # 检查是否“看起来像IP，但其实无效” (例如: 123.456.789.0)
        if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
            responses = [
                f"「{ip}」...这个地址...我看不懂，但我大受震撼。",
                f"你这IP地址是体育老师教的吗？（指 {ip}）",
                f"正在连接 {ip}... 连接失败。错误代码：256 (数字太大，路由器聊爆了)",
            ]
            await mc_status.finish(random.choice(responses))

        # 检查是否像人名或单词
        if re.search(r'[\u4e00-\u9fa5]{2,4}|[A-Za-z]{3,}', ip):
            name_responses = [
                f"「{ip}」大佬的服务器需要VIP通行证🎫",
                f"正在连接 {ip} 的心跳服务器...信号强度：❤️❤️❤️",
                f"该服务器需要 {ip} 的指纹验证才能访问🖐️",
                f"你输入的是...人名？抱歉，本机器人没有「{ip}」的好友，无法查询。",
            ]
            await mc_status.finish(random.choice(name_responses))

        # --- 3. 通用兜底区 (适用于其他所有情况) ---
        general_responses = [
            f"「{ip}」服务器状态：正在加载存在感...0%",
            f"警告：'{ip}' 触发路由器颜文字防御系统 (╯°□°)╯︵ ┻━┻",
            f"正在向 {ip} 发送脑电波...对方已读不回📵",
            f"该地址过于抽象，需要安装'理解补丁'才能访问🧩",
            f"系统将 '{ip}' 自动翻译为：爱的告白服务器💌",
            f"Pinging {ip}... Request timed out. (它好像...跑路了)",
            f"「{ip}」？你这串神秘代码是不是克苏鲁的召唤咒语？SAN值狂掉...😨",
        ]
        await mc_status.finish(random.choice(general_responses))

    try:
        await mc_status.send(f"正在查询服务器 {ip} 的状态...")

        # 1. 获取实时服务器状态
        live_status_data = await get_single_server_status(ip)

        # 2. 获取本地存储的服务器配置信息
        saved_config = get_server_info(event.group_id, ip)

        # 3. 合并信息
        if saved_config:
            # 如果找到了本地配置，直接用它与实时状态合并
            # 本地配置(saved_config)的值会覆盖实时状态(live_status_data)中的同名字段
            final_server_data = {**live_status_data, **saved_config}
        else:
            # 如果在本地配置中没找到该服务器，直接使用实时状态
            final_server_data = live_status_data

        # 4. 移除子服信息，确保只渲染查询的单个服务器
        final_server_data.pop('children', None)

        # 5. 使用处理后的数据生成图片
        image_path = await render_status_image([final_server_data], event.group_id, True)
        reply_message = MessageSegment.image(file=f"file:///{image_path}")
    except MatcherException:
        raise
    except Exception as e:
        reply_message = f"查询 {ip} 失败: {e}"
    await mc_status.finish(reply_message)


async def handle_list_simple(bot: Bot, event: GroupMessageEvent):
    from . import mc_status
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
            hide_ip = s.get('hide_ip', False)
            display_name = s.get('display_name', '')
            
            # 根据 hide_ip 和 display_name 决定地址部分的显示内容
            address_part = ""
            if hide_ip:
                address_part = display_name if display_name else "[IP已隐藏]"
            else:
                address_part = ip
            
            # 将注释作为独立的补充信息
            comment_part = f" ({comment})" if comment else ""

            prefix = f"[{tag}] " if tag else ""
            indent = "  " * level
            connector = "↳ " if level > 0 else ""
            
            lines.append(f"{indent}{connector}{prefix}{address_part}{comment_part}")
            
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

SUBCOMMAND_HANDLERS = {
    "add": _handle_add,
    "remove": _handle_remove,
    "rm": _handle_remove,
    "footer": _handle_footer,
    "set": _handle_set,
    "clear": _handle_clear,
    "list": _handle_list,
    "edit": _handle_edit,
    "export_json": _handle_export_json,
    # "import" is now handled privately
    "help": _handle_help,
}


