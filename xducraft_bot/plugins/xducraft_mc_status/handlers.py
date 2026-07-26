"""``/mcs`` 各子命令的实现。

三个贯穿全文件的约定：

1. **权限检查用 :func:`admin_only` 装饰器**，不再每个函数开头抄一遍
   ``if not await is_admin(...)``。
2. **管理类操作的回执默认走私聊**（见 ``/mcs quiet``）。机器人接在几百人的大群
   里，改一次配置就在群里回一条，很快就是刷屏。
3. **群级 / 全局两级配置由 :class:`ScopedSetting` 统一处理**。旧代码里
   ``/mcs source`` 和 ``/mcs api`` 是两份逐行对应的实现，加一个新配置项就要再抄
   一份。
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment, PrivateMessageEvent
from nonebot.log import logger

from xducraft_bot.shared.onebot import make_node, notify_privately, send_private_forward, send_text_sections

from . import auth_mode as auth
from .config_coder import compress_config, decompress_config
from .constants import USAGE_ADMIN, USAGE_USER, WEB_UI_BASE_URL
from .data_manager import (
    VALID_API_SOURCES, add_footer, add_server, clear_footer, clear_global_status_api_source,
    clear_global_status_api_url, clear_group_status_api_source, clear_group_status_api_url,
    clear_server_attribute, export_group_data, get_all_servers_flat, get_auth_detect_enabled,
    get_effective_status_api_source, get_effective_status_api_url, get_group_default_auth_mode,
    get_quiet_admin_replies, get_server_info, get_server_list, import_group_data, remove_server,
    set_auth_detect_enabled, set_global_status_api_source, set_global_status_api_url,
    set_group_default_auth_mode, set_group_status_api_source, set_group_status_api_url,
    set_quiet_admin_replies, set_server_attribute,
)
from .decode_image import get_cache_stats
from .image_renderer import render_status_image
from .status_fetcher import get_all_servers_status, get_single_server_status
from .utils import (
    get_server_display_address, is_admin, is_valid_api_url, is_valid_hex_color,
    is_valid_server_address,
)

#: ``/mcs edit`` 之后等待私聊导入的用户： user_id -> (group_id, 发起时间)
#:
#: 旧实现只存 user_id -> group_id 且**永不过期**：管理员点了 edit 之后忘了导入，
#: 这条状态会一直留着，几个月后他在另一个群随手发一条 import 就会把当初那个群的
#: 配置覆盖掉。现在加了有效期。
EDITING_USERS: Dict[int, Tuple[int, float]] = {}
EDIT_SESSION_TTL = 30 * 60


def _matcher():
    """延迟拿 matcher，避免和 ``__init__`` 形成循环导入。"""
    from . import mc_status

    return mc_status


def _prune_edit_sessions() -> None:
    now = time.time()
    for user_id in [uid for uid, (_, started) in EDITING_USERS.items() if now - started > EDIT_SESSION_TTL]:
        EDITING_USERS.pop(user_id, None)


def start_edit_session(user_id: int, group_id: int) -> None:
    _prune_edit_sessions()
    EDITING_USERS[user_id] = (int(group_id), time.time())


def take_edit_session(user_id: int) -> Optional[int]:
    """取出并消费一次编辑会话；已过期或不存在返回 None。"""
    _prune_edit_sessions()
    entry = EDITING_USERS.pop(user_id, None)
    return entry[0] if entry else None


# ==============================================================================
# 回复辅助
# ==============================================================================

async def _finish(text: str) -> None:
    await _matcher().finish(text)


async def _finish_admin(bot: Bot, event: GroupMessageEvent, text: str) -> None:
    """管理类操作的回执。

    开启安静模式时私聊发给操作者；私聊不通（没加好友）再退回群里，
    保证操作者一定看得到结果。
    """
    matcher = _matcher()
    if get_quiet_admin_replies(event.group_id) and await notify_privately(bot, event.user_id, text):
        await matcher.finish()
    await matcher.finish(text)


def admin_only(handler: Callable) -> Callable:
    """要求群管理员 / 群主 / SUPERUSER。"""

    @wraps(handler)
    async def wrapper(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
        if not await is_admin(bot, event):
            await _finish("这条命令只有群管理员可以使用。")
        return await handler(bot, event, arg_list)

    return wrapper


# ==============================================================================
# 群级 / 全局两级配置
# ==============================================================================

@dataclass
class ScopedSetting:
    """一个支持“群级覆盖 + 全局默认”的配置项。

    ``/mcs source`` 和 ``/mcs api`` 的全部子命令语法都由这里生成，
    两者只是校验函数和文案不同。
    """

    command: str                 # 子命令名，如 "source"
    title: str                   # 展示名，如 "状态查询源"
    value_hint: str              # 取值提示，如 "protocol / sjtu / jsu / custom / auto"
    normalize: Callable[[str], Optional[str]]        # 输入 -> 标准值 / None 表示非法
    describe: Callable[[str], str]                   # 标准值 -> 展示文本
    get_effective: Callable[[int], Tuple[str, str]]
    set_group: Callable[[int, str], bool]
    clear_group: Callable[[int], bool]
    set_global: Callable[[str], bool]
    clear_global: Callable[[], bool]
    allow_shorthand: bool = False   # 是否兼容 "/mcs source <值>" 这种老写法

    @property
    def usage(self) -> str:
        lines = [
            f"/mcs {self.command} — 查看当前生效值",
            f"/mcs {self.command} set <值> — 设置本群",
            f"/mcs {self.command} clear — 清除本群覆盖",
            f"/mcs {self.command} global set <值> — 设置全局默认",
            f"/mcs {self.command} global clear — 清除全局默认",
            f"可用值：{self.value_hint}",
        ]
        return "\n".join(lines)


SCOPE_NAMES = {"group": "本群配置", "global": "全局默认", "none": "未配置"}


async def _handle_scoped_setting(
    bot: Bot, event: GroupMessageEvent, arg_list: List[str], setting: ScopedSetting
) -> None:
    """``ScopedSetting`` 的统一分发。"""
    args = arg_list[1:]

    if not args:
        value, scope = setting.get_effective(event.group_id)
        scope_name = SCOPE_NAMES.get(scope, scope)
        current = setting.describe(value) if value else "未配置"
        await _finish(f"当前{setting.title}（{scope_name}）：{current}\n\n{setting.usage}")

    action = args[0].strip().lower()

    # 兼容老写法 "/mcs source jsu"
    if setting.allow_shorthand and len(args) == 1 and action not in {"set", "clear", "global"}:
        normalized = setting.normalize(action)
        if normalized is None:
            await _finish(f"无法识别的值：{args[0]}\n\n{setting.usage}")
        changed = setting.set_group(event.group_id, normalized)
        verb = "已设置" if changed else "未变化"
        await _finish_admin(bot, event, f"{verb}本群{setting.title}：{setting.describe(normalized)}")

    if action == "set":
        if len(args) != 2:
            await _finish(f"用法：/mcs {setting.command} set <值>\n可用值：{setting.value_hint}")
        normalized = setting.normalize(args[1])
        if normalized is None:
            await _finish(f"无法识别的值：{args[1]}\n可用值：{setting.value_hint}")
        changed = setting.set_group(event.group_id, normalized)
        verb = "已设置" if changed else "未变化"
        await _finish_admin(bot, event, f"{verb}本群{setting.title}：{setting.describe(normalized)}")

    if action == "clear":
        if setting.clear_group(event.group_id):
            value, scope = setting.get_effective(event.group_id)
            fallback = setting.describe(value) if value else "未配置"
            await _finish_admin(
                bot, event,
                f"已清除本群{setting.title}覆盖，现在回退到{SCOPE_NAMES.get(scope, scope)}：{fallback}",
            )
        await _finish_admin(bot, event, f"本群原本就没有设置{setting.title}覆盖。")

    if action == "global":
        if len(args) == 3 and args[1].strip().lower() == "set":
            normalized = setting.normalize(args[2])
            if normalized is None:
                await _finish(f"无法识别的值：{args[2]}\n可用值：{setting.value_hint}")
            changed = setting.set_global(normalized)
            verb = "已设置" if changed else "未变化"
            await _finish_admin(bot, event, f"{verb}全局默认{setting.title}：{setting.describe(normalized)}")

        if len(args) == 2 and args[1].strip().lower() == "clear":
            if setting.clear_global():
                await _finish_admin(bot, event, f"已清除全局默认{setting.title}。")
            await _finish_admin(bot, event, f"全局默认{setting.title}原本就是默认值。")

        await _finish(f"用法：\n/mcs {setting.command} global set <值>\n/mcs {setting.command} global clear")

    await _finish(f"未知参数：{args[0]}\n\n{setting.usage}")


SOURCE_LABELS = {
    "protocol": "本地协议直连",
    "sjtu": "SJTU 聚合 API",
    "jsu": "JSU API",
    "custom": "自定义后端 API",
    "auto": "自动回退（协议 → 自定义 → JSU → SJTU）",
}

SOURCE_SETTING = ScopedSetting(
    command="source",
    title="状态查询源",
    value_hint="protocol / sjtu / jsu / custom / auto",
    normalize=lambda value: value.strip().lower() if value.strip().lower() in VALID_API_SOURCES else None,
    describe=lambda value: f"{SOURCE_LABELS.get(value, value)}（{value}）",
    get_effective=get_effective_status_api_source,
    set_group=set_group_status_api_source,
    clear_group=clear_group_status_api_source,
    set_global=set_global_status_api_source,
    clear_global=clear_global_status_api_source,
    allow_shorthand=True,
)

API_SETTING = ScopedSetting(
    command="api",
    title="自定义后端地址",
    value_hint="以 http:// 或 https:// 开头的完整地址",
    normalize=lambda value: value.strip() if is_valid_api_url(value) else None,
    describe=lambda value: value,
    get_effective=get_effective_status_api_url,
    set_group=set_group_status_api_url,
    clear_group=clear_group_status_api_url,
    set_global=set_global_status_api_url,
    clear_global=clear_global_status_api_url,
)


@admin_only
async def _handle_source(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    await _handle_scoped_setting(bot, event, arg_list, SOURCE_SETTING)


@admin_only
async def _handle_api(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    await _handle_scoped_setting(bot, event, arg_list, API_SETTING)


# ==============================================================================
# 服务器增删改
# ==============================================================================

@admin_only
async def _handle_add(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    if len(arg_list) < 2:
        await _finish("用法：/mcs add <IP[:端口]>\n例如：/mcs add mc.example.com:25565")

    ip = arg_list[1]
    if not is_valid_server_address(ip):
        await _finish(f"这不是一个有效的服务器地址：{ip}\n支持域名、IPv4、IPv6，可带 :端口。")

    if add_server(event.group_id, ip):
        await _finish_admin(bot, event, f"已添加服务器：{ip}\n可以用 /mcs set {ip} tag <标签> 给它加个标签。")
    await _finish_admin(bot, event, f"添加失败：{ip} 已经在本群的列表里了。")


@admin_only
async def _handle_remove(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    if len(arg_list) < 2:
        await _finish("用法：/mcs remove <IP>\n可以先用 /mcs list 查看已添加的地址。")

    ip = arg_list[1]
    if remove_server(event.group_id, ip):
        await _finish_admin(bot, event, f"已移除服务器：{ip}（它的子服务器也一并移除了）")
    await _finish_admin(bot, event, f"移除失败：本群没有找到 {ip}。用 /mcs list 看看确切地址。")


#: ``/mcs set`` 支持的属性 -> (说明, 校验/转换函数)
def _parse_bool(value: str) -> Optional[bool]:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y", "on", "是", "开"}:
        return True
    if lowered in {"false", "0", "no", "n", "off", "否", "关"}:
        return False
    return None


def _parse_tag_color(value: str) -> Optional[str]:
    candidate = value.strip().lstrip("#")
    return candidate.upper() if is_valid_hex_color(candidate) else None


def _parse_priority(value: str) -> Optional[int]:
    try:
        return int(value.strip())
    except ValueError:
        return None


SETTABLE_ATTRIBUTES: Dict[str, Tuple[str, Callable[[str], Any]]] = {
    "tag": ("标签文字", lambda value: value),
    "tag_color": ("标签底色，6 位十六进制如 3498DB", _parse_tag_color),
    "comment": ("服务器名称/备注", lambda value: value),
    "display_name": ("图片中的线路名称/连接提示（设置后自动隐藏查询地址）", lambda value: value),
    "auth_mode": ("登录验证方式：XDU / MUA / 正版 / 外置 / 离线 / 混合", auth.normalize_mode),
    "hide_ip": ("是否隐藏 IP：on / off", _parse_bool),
    "ignore_in_list": ("是否在列表中隐藏：on / off", _parse_bool),
    "priority": ("排序优先级，数字越小越靠前", _parse_priority),
}


@admin_only
async def _handle_set(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    if len(arg_list) < 4:
        lines = [f"  {name} — {desc}" for name, (desc, _) in SETTABLE_ATTRIBUTES.items()]
        await _finish("用法：/mcs set <IP> <属性> <值>\n可设置的属性：\n" + "\n".join(lines))

    ip, attribute, raw_value = arg_list[1], arg_list[2].lower(), " ".join(arg_list[3:])

    if attribute == "parent_ip":
        await _finish("父子关系不能用 /mcs set 修改。\n请用 /mcs edit 打开网页编辑器，拖拽调整层级。")

    if attribute not in SETTABLE_ATTRIBUTES:
        await _finish(
            f"不支持的属性：{attribute}\n可用属性：{'、'.join(SETTABLE_ATTRIBUTES)}"
        )

    description, parser = SETTABLE_ATTRIBUTES[attribute]
    value = parser(raw_value)
    if value is None:
        await _finish(f"「{raw_value}」不是合法的取值。\n{attribute} — {description}")

    if not get_server_info(event.group_id, ip):
        await _finish(f"本群没有找到服务器 {ip}。用 /mcs list 看看确切地址。")

    if set_server_attribute(event.group_id, ip, attribute, value):
        if attribute == "display_name" and str(value).strip():
            set_server_attribute(event.group_id, ip, "hide_ip", True)
        shown = auth.style_for(value).label if attribute == "auth_mode" and value else value
        suffix = "（已自动隐藏实际查询地址）" if attribute == "display_name" and str(value).strip() else ""
        await _finish_admin(bot, event, f"已设置 {ip} 的 {attribute} = {shown}{suffix}")
    await _finish_admin(bot, event, f"设置失败：{ip} 不存在。")


@admin_only
async def _handle_clear(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    if len(arg_list) != 3:
        await _finish(f"用法：/mcs clear <IP> <属性>\n可重置的属性：{'、'.join(SETTABLE_ATTRIBUTES)}")

    ip, attribute = arg_list[1], arg_list[2].lower()
    if attribute not in SETTABLE_ATTRIBUTES:
        await _finish(f"不支持的属性：{attribute}\n可用属性：{'、'.join(SETTABLE_ATTRIBUTES)}")

    if clear_server_attribute(event.group_id, ip, attribute):
        await _finish_admin(bot, event, f"已重置 {ip} 的 {attribute}。")
    await _finish_admin(bot, event, f"重置失败：本群没有找到 {ip}。")


@admin_only
async def _handle_footer(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    if len(arg_list) == 1:
        from .data_manager import get_footer

        current = get_footer(event.group_id)
        await _finish(f"当前页脚：{current}" if current else "还没有设置页脚。\n用法：/mcs footer <文本>")

    if arg_list[1].lower() == "clear":
        clear_footer(event.group_id)
        await _finish_admin(bot, event, "已清除页脚文本。")

    footer_text = " ".join(arg_list[1:])
    add_footer(event.group_id, footer_text)
    await _finish_admin(bot, event, f"已设置页脚：{footer_text}")


@admin_only
async def _handle_quiet(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    """管理指令回执是否走私聊。"""
    if len(arg_list) == 1:
        state = "开启" if get_quiet_admin_replies(event.group_id) else "关闭"
        await _finish(
            f"安静模式：{state}\n"
            "开启后，管理类指令的回执会私聊发给操作者，不在群里刷屏。\n"
            "用法：/mcs quiet on|off"
        )

    parsed = _parse_bool(arg_list[1])
    if parsed is None:
        await _finish("用法：/mcs quiet on|off")

    set_quiet_admin_replies(event.group_id, parsed)
    # 这条回执必须让操作者看到，且开/关的语义刚好相反，所以直接回群。
    await _finish(f"已{'开启' if parsed else '关闭'}安静模式。管理指令回执将{'私聊发送' if parsed else '发在群里'}。")


# ==============================================================================
# 登录验证方式
# ==============================================================================

AUTH_USAGE = (
    "用法：\n"
    "/mcs auth — 查看本群所有服务器的登录验证方式\n"
    "/mcs auth set <IP> <验证方式> — 指定某台服务器\n"
    "/mcs auth clear <IP> — 清除单服配置并回退本群默认值\n"
    "/mcs auth default <验证方式|clear> — 设置本群默认\n"
    "/mcs auth detect on|off — 开关尽力而为的自动探测（默认关）\n"
    "验证方式可填：XDU / MUA / 正版 / 外置 / 离线 / 混合\n"
    "提示：MUA 是包含 XDU 的联合认证；标记为 MUA 的服务器可直接使用 XDU 账号登录。"
)


def _auth_overview(group_id: int) -> str:
    """把本群所有服务器的验证方式列成一段文本。"""
    servers = get_all_servers_flat(group_id)
    if not servers:
        return "本群还没有添加任何服务器。"

    group_default = get_group_default_auth_mode(group_id)
    lines = []
    for server in servers:
        resolved = auth.resolve_auth(server, group_default)
        address = get_server_display_address(server)
        marker = "✔" if resolved.confirmed else "·"
        line = f"{marker} {address} → {resolved.style.label}"
        if resolved.conflict:
            line += f"（实测为 {auth.style_for(resolved.detected).label}，与配置不一致）"
        lines.append(line)

    header = [
        "本群服务器登录验证方式：",
        "  ✔ = 已由在线玩家样本实测确认    · = 按配置显示",
    ]
    if group_default:
        header.append(f"  本群默认：{auth.style_for(group_default).label}")
    header.append(f"  自动探测：{'开启' if get_auth_detect_enabled(group_id) else '关闭'}")
    return "\n".join(header + [""] + lines)


async def _handle_auth(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    args = arg_list[1:]

    # 查看对所有人开放，修改才需要管理员。
    if not args:
        await _finish(_auth_overview(event.group_id) + "\n\n" + AUTH_USAGE)

    action = args[0].strip().lower()

    if not await is_admin(bot, event):
        await _finish("查看请直接发送 /mcs auth；修改验证方式需要群管理员权限。")

    if action == "set":
        if len(args) != 3:
            await _finish("用法：/mcs auth set <IP> <XDU|MUA|正版|外置|离线|混合>")
        ip, raw_mode = args[1], args[2]
        mode = auth.normalize_mode(raw_mode)
        if mode is None:
            await _finish(
                f"无法识别的验证方式：{raw_mode}\n"
                "可填：XDU / MUA / 正版 / 外置 / 离线 / 混合"
            )
        if not mode:
            await _finish("要清除单服配置并回退本群默认值，请用：/mcs auth clear <IP>")
        if not get_server_info(event.group_id, ip):
            await _finish(f"本群没有找到服务器 {ip}。用 /mcs list 看看确切地址。")

        set_server_attribute(event.group_id, ip, "auth_mode", mode)
        await _finish_admin(bot, event, f"已将 {ip} 的登录验证方式设为：{auth.style_for(mode).label}")

    if action == "clear":
        if len(args) != 2:
            await _finish("用法：/mcs auth clear <IP>")
        ip = args[1]
        if not get_server_info(event.group_id, ip):
            await _finish(f"本群没有找到服务器 {ip}。")
        clear_server_attribute(event.group_id, ip, "auth_mode")
        await _finish_admin(
            bot,
            event,
            f"已清除 {ip} 的验证方式配置，将回退本群默认值；"
            "若本群也未设置默认值，则不显示验证方式。",
        )

    if action == "default":
        if len(args) != 2:
            await _finish("用法：/mcs auth default <XDU|MUA|正版|外置|离线|混合|clear>")
        raw = args[1].strip().lower()
        if raw == "clear":
            set_group_default_auth_mode(event.group_id, "")
            await _finish_admin(bot, event, "已清除本群默认验证方式。")
        mode = auth.normalize_mode(raw)
        if not mode:
            await _finish(f"无法识别的验证方式：{args[1]}")
        set_group_default_auth_mode(event.group_id, mode)
        await _finish_admin(
            bot, event,
            f"已将本群默认验证方式设为：{auth.style_for(mode).label}\n"
            "（只对没有单独配置的服务器生效）",
        )

    if action == "detect":
        if len(args) != 2:
            await _finish("用法：/mcs auth detect on|off")
        parsed = _parse_bool(args[1])
        if parsed is None:
            await _finish("用法：/mcs auth detect on|off")
        set_auth_detect_enabled(event.group_id, parsed)
        await _finish_admin(
            bot, event,
            f"已{'开启' if parsed else '关闭'}登录验证方式自动探测。\n"
            + (
                "此功能只能根据在线玩家 UUID 尝试推断，联合认证可能无法区分，"
                "建议以显式配置为准。"
                if parsed else "今后只按显式配置或本群默认值显示。"
            ),
        )

    await _finish(f"未知参数：{args[0]}\n\n{AUTH_USAGE}")


# ==============================================================================
# 查询
# ==============================================================================

async def handle_query_all(bot: Bot, event: GroupMessageEvent, show_all_servers: bool):
    """查询本群所有服务器并出图。"""
    matcher = _matcher()

    servers = get_server_list(event.group_id)
    if not servers:
        await matcher.finish(
            "本群还没有添加 Minecraft 服务器。\n"
            "管理员可以用 /mcs add <IP> 添加，或用 /mcs edit 打开网页编辑器。"
        )

    try:
        source, _ = get_effective_status_api_source(event.group_id)
        server_data_list = await get_all_servers_status(event.group_id)
        image_path = await render_status_image(server_data_list, event.group_id, show_all_servers, source_label=source)
    except Exception as exc:
        logger.exception("[MCStatus] 查询群 {} 全部服务器失败", event.group_id)
        await matcher.finish(f"查询失败：{type(exc).__name__}: {exc}\n管理员可用 /mcs diag 排查。")

    await matcher.finish(MessageSegment.image(file=f"file:///{image_path}"))


#: 一些明显不是服务器地址的输入，与其冷冰冰地报错不如接个梗。
def _easter_egg_reply(ip: str) -> Optional[str]:
    if ip in {"127.0.0.1", "localhost", "::1"}:
        return random.choice([
            "你搁这儿开单机呢？查询 127.0.0.1……找到了！在你电脑里！",
            "查询 localhost……连接成功！……等等，我为什么要查我自己？Σ( ° △ °|||)",
        ])
    if ip in {"192.168.1.1", "192.168.0.1"}:
        return "你查路由器干嘛！是不是想改 WiFi 密码不让我上了！(°òДó)ﾉ"
    if "❤" in ip:
        return "❤ 服务器？这怕不是运行在我的心巴上！"
    if "114514" in ip:
        return f"查询 {ip} 中……哼哼啊啊啊啊啊啊（查询失败）"
    if ip == "404":
        return "Server Not Found.（你看，404 自己都说找不到了）"
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
        return random.choice([
            f"「{ip}」……这个地址……我看不懂，但我大受震撼。",
            f"正在连接 {ip}…… 失败。错误代码：256（数字太大，路由器聊爆了）",
        ])
    if re.search(r"[一-龥]{2,4}|[A-Za-z]{3,}", ip):
        return random.choice([
            f"「{ip}」大佬的服务器需要 VIP 通行证🎫",
            f"正在连接 {ip} 的心跳服务器……信号强度：❤️❤️❤️",
            f"你输入的是……人名？抱歉，本机器人没有「{ip}」的好友，无法查询。",
        ])
    return random.choice([
        f"「{ip}」服务器状态：正在加载存在感……0%",
        f"正在向 {ip} 发送脑电波……对方已读不回📵",
        f"Pinging {ip}... Request timed out.（它好像……跑路了）",
    ])


async def handle_query_single(bot: Bot, event: GroupMessageEvent, ip: str):
    """查询单个服务器。"""
    matcher = _matcher()

    if not is_valid_server_address(ip):
        await matcher.finish(_easter_egg_reply(ip))

    try:
        source, _ = get_effective_status_api_source(event.group_id)
        live_status = await get_single_server_status(ip, group_id=event.group_id)

        saved_config = get_server_info(event.group_id, ip)
        if saved_config:
            # 本地配置（标签、备注、验证方式）覆盖实时状态里的同名字段。
            final_data = {**live_status, **{k: v for k, v in saved_config.items() if k != "children"}}
        else:
            final_data = dict(live_status)
        final_data.pop("children", None)

        if get_auth_detect_enabled(event.group_id):
            await auth.annotate_servers([final_data])

        image_path = await render_status_image([final_data], event.group_id, True, source_label=source)
    except Exception as exc:
        logger.exception("[MCStatus] 查询 {} 失败", ip)
        await matcher.finish(f"查询 {ip} 失败：{type(exc).__name__}: {exc}")

    await matcher.finish(MessageSegment.image(file=f"file:///{image_path}"))


async def handle_list_simple(bot: Bot, event: GroupMessageEvent):
    """``/mcs list``：树形列出已添加的服务器。"""
    matcher = _matcher()
    server_tree = get_server_list(event.group_id)

    if not server_tree:
        await matcher.finish("本群还没有添加任何服务器。\n管理员可用 /mcs add <IP> 添加。")

    group_default = get_group_default_auth_mode(event.group_id)

    def format_tree(nodes: List[Dict[str, Any]], level: int = 0) -> List[str]:
        lines = []
        for node in nodes:
            address = get_server_display_address(node)
            tag = f"[{node['tag']}] " if node.get("tag") else ""
            comment = f"（{node['comment']}）" if node.get("comment") else ""
            resolved = auth.resolve_auth(node, group_default)
            badge = f" · {resolved.style.short_label}" if resolved.mode != auth.MODE_UNKNOWN else ""
            prefix = "  " * level + ("↳ " if level else "")
            lines.append(f"{prefix}{tag}{address}{comment}{badge}")
            if node.get("children"):
                lines.extend(format_tree(node["children"], level + 1))
        return lines

    body = "已添加的服务器：\n" + "\n".join(format_tree(server_tree))
    await send_text_sections(bot, event, [body], title="服务器列表")
    await matcher.finish()


async def _handle_list(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    if len(arg_list) > 1:
        await _finish("用法：/mcs list（不接参数）\n想看验证方式请用 /mcs auth。")
    await handle_list_simple(bot, event)


@admin_only
async def _handle_diag(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    """``/mcs diag``：配置概览 + 各数据源实测连通性。"""
    matcher = _matcher()
    group_id = event.group_id

    source, source_scope = get_effective_status_api_source(group_id)
    api_url, url_scope = get_effective_status_api_url(group_id)
    servers = get_all_servers_flat(group_id)
    cache = get_cache_stats()

    lines = [
        "【本群配置】",
        f"服务器数量：{len(servers)}",
        f"状态查询源：{SOURCE_LABELS.get(source, source)}（{source}，来自{SCOPE_NAMES.get(source_scope, source_scope)}）",
        f"自定义后端：{api_url or '未配置'}（{SCOPE_NAMES.get(url_scope, url_scope)}）",
        f"验证方式自动探测：{'开启' if get_auth_detect_enabled(group_id) else '关闭'}",
        f"本群默认验证方式：{auth.style_for(get_group_default_auth_mode(group_id)).label if get_group_default_auth_mode(group_id) else '未设置'}",
        f"安静模式：{'开启' if get_quiet_admin_replies(group_id) else '关闭'}",
        f"图标缓存：{cache['valid_files']}/{cache['total_files']} 有效，共 {cache['total_size_mb']} MB",
    ]

    if servers:
        probe_ip = servers[0].get("ip", "")
        lines += ["", f"【连通性实测】目标：{probe_ip}"]
        from .status_fetcher import _fetch_via_custom, _fetch_via_jsu, _fetch_via_protocol, _fetch_via_sjtu

        probes = [("protocol", _fetch_via_protocol(probe_ip)),
                  ("jsu", _fetch_via_jsu(probe_ip)),
                  ("sjtu", _fetch_via_sjtu(probe_ip))]
        if api_url:
            probes.append(("custom", _fetch_via_custom(probe_ip, api_url)))

        for name, coroutine in probes:
            try:
                result = await coroutine
            except Exception as exc:
                lines.append(f"  {name}: 异常 {type(exc).__name__}: {exc}")
                continue
            if result.get("online"):
                lines.append(f"  {name}: ✔ 在线，{result.get('ping', 0)}ms")
            else:
                lines.append(f"  {name}: ✘ {str(result.get('error') or '未知错误')[:120]}")

    await send_text_sections(bot, event, ["\n".join(lines)], title="MC 状态诊断")
    await matcher.finish()


# ==============================================================================
# 配置导入导出
# ==============================================================================

@admin_only
async def _handle_edit(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    """生成网页编辑器链接，私聊发给操作者。"""
    matcher = _matcher()
    user_id, group_id = event.user_id, event.group_id

    group_data = export_group_data(group_id) or {}
    compressed = compress_config(group_data)
    if not compressed:
        await matcher.finish("导出失败：压缩配置时出错，请联系维护者查看日志。")

    export_url = f"{WEB_UI_BASE_URL}?data={compressed}"

    sent = await notify_privately(
        bot, user_id,
        "点击下面的链接打开网页编辑器，改完之后按页面提示复制导入命令，"
        f"再在这个私聊里发送即可。\n"
        f"链接 {EDIT_SESSION_TTL // 60} 分钟内有效，且只接受一次导入。",
    )
    if not sent:
        await matcher.finish(
            "没能给你发私信。请先加机器人好友，或在群里点一下机器人头像发起临时会话，然后重试 /mcs edit。"
        )

    # 链接很长，用合并转发发送，避免被聊天框折行截断。
    if not await send_private_forward(bot, user_id, [make_node(export_url, "网页编辑器链接", event.self_id)]):
        await notify_privately(bot, user_id, export_url)

    start_edit_session(user_id, group_id)
    await _finish_admin(bot, event, "编辑链接已通过私信发送，请查收。")


@admin_only
async def _handle_export_json(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    """私聊导出原始 JSON，用于排查问题。"""
    matcher = _matcher()
    group_data = export_group_data(event.group_id) or {}

    try:
        payload = json.dumps(group_data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        await matcher.finish(f"序列化配置失败：{exc}")

    nodes = [make_node(f"群 {event.group_id} 的原始配置：\n{payload}", "JSON 导出", event.self_id)]
    if not await send_private_forward(bot, event.user_id, nodes):
        await matcher.finish("发送失败。请先加机器人好友，或开启临时会话后重试。")

    await _finish_admin(bot, event, "已通过私信发送 JSON 配置。")


async def handle_private_import(bot: Bot, event: PrivateMessageEvent, arg_list: List[str]):
    """私聊里的 ``/mcs import <压缩字符串>``。"""
    matcher = _matcher()
    user_id = event.user_id

    group_id = take_edit_session(user_id)
    if group_id is None:
        await matcher.finish(
            "没有找到进行中的编辑会话。\n"
            "请先在需要修改的群里发送 /mcs edit，拿到链接后再回来导入。"
            f"（编辑会话 {EDIT_SESSION_TTL // 60} 分钟内有效）"
        )

    if len(arg_list) != 2:
        # 会话已经被取出来了，格式不对就放回去，别让用户白跑一趟 /mcs edit。
        start_edit_session(user_id, group_id)
        await matcher.finish("格式不对。请发送：/mcs import <网页里复制的字符串>")

    decompressed = decompress_config(arg_list[1])
    if decompressed is None:
        start_edit_session(user_id, group_id)
        await matcher.finish("导入失败：无法解析这段字符串。请确认是从网页编辑器完整复制的。")

    if not import_group_data(group_id, decompressed):
        start_edit_session(user_id, group_id)
        await matcher.finish("导入失败：数据结构不符合要求。")

    group_name = str(group_id)
    try:
        info = await bot.get_group_info(group_id=group_id)
        group_name = info.get("group_name", group_name) or group_name
    except Exception:
        pass  # 机器人可能已经不在这个群了，用群号兜底即可。

    server_count = len(get_all_servers_flat(group_id))
    await matcher.finish(f"群「{group_name}」的配置导入成功，共 {server_count} 台服务器。")


# ==============================================================================
# 帮助
# ==============================================================================

async def _handle_help(bot: Bot, event: GroupMessageEvent, arg_list: List[str]):
    matcher = _matcher()
    if not await is_admin(bot, event):
        await send_text_sections(bot, event, [USAGE_USER], title="MC 状态 · 帮助")
        await matcher.finish()

    sections = [section.strip() for section in USAGE_ADMIN.split("---") if section.strip()]
    await send_text_sections(bot, event, sections, title="MC 状态 · 管理员帮助")
    await matcher.finish()


SUBCOMMAND_HANDLERS: Dict[str, Callable] = {
    "add": _handle_add,
    "remove": _handle_remove,
    "rm": _handle_remove,
    "del": _handle_remove,
    "footer": _handle_footer,
    "set": _handle_set,
    "clear": _handle_clear,
    "list": _handle_list,
    "auth": _handle_auth,
    "edit": _handle_edit,
    "editor": _handle_edit,
    "export": _handle_edit,
    "export_json": _handle_export_json,
    "source": _handle_source,
    "api": _handle_api,
    "quiet": _handle_quiet,
    "diag": _handle_diag,
    "help": _handle_help,
}

__all__ = [
    "SUBCOMMAND_HANDLERS", "handle_query_all", "handle_query_single",
    "handle_list_simple", "handle_private_import", "EDITING_USERS",
]
