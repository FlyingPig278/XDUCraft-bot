import ipaddress
import re
from urllib.parse import urlparse

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.permission import SUPERUSER

# 屏蔽危险网站
BLACKLISTED_PATTERNS = [
    'gov.cn',
    'mil.cn',
]

async def is_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    """检查用户是否是群管理员、群主或超级用户。"""
    # 检查是否是超级用户
    if await SUPERUSER(bot, event):
        return True
    # 检查是否是群管理员或群主
    if isinstance(event, GroupMessageEvent):
        return event.sender.role in ["admin", "owner"]
    return False


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
