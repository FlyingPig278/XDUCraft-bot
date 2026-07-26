"""地址校验等小工具。

``is_admin`` 现在住在 :mod:`xducraft_bot.shared.permissions`——词云、猪猪图、
happy_bot 三个插件曾经为了一个权限函数 import 整个 MC 状态插件，那是明显的
分层错误。这里保留一个再导出，老的 import 路径继续可用。
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping
from urllib.parse import urlparse

from xducraft_bot.shared.permissions import can_manage, is_admin, is_superuser  # noqa: F401

#: 明确不允许查询的域名后缀。
BLACKLISTED_PATTERNS = [
    "gov.cn",
    "mil.cn",
]


def format_address_for_pixel_font(value: Any) -> str:
    """给像素字体中的地址分隔符留出呼吸空间。

    Minecraft AE 的点号和冒号非常贴近相邻字符，域名、IPv4 与端口容易糊成一团。
    旧渲染器会在 ``.``、``:`` 和线路分隔 ``|`` 两侧加空格；这里把这项规则集中
    起来，并同时用于查询地址与管理员填写的线路说明。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s*\.\s*", " . ", text)
    text = re.sub(r"\s*:\s*", " : ", text)
    return re.sub(r"\s*\|\s*", "   |   ", text)


def get_server_display_address(
    server: Mapping[str, Any],
    *,
    pixel_font: bool = False,
) -> str:
    """按兼容旧配置的规则解析一台服务器应该展示的地址。

    ``ip`` 始终是实际查询目标；``hide_ip + display_name`` 是旧配置沿用至今的
    存储形式。新版编辑器只把它们包装成“原地址 / 自定义线路说明 / 完全隐藏”
    三种显示方式，不需要迁移已有数据。
    """
    if bool(server.get("hide_ip")):
        address = str(server.get("display_name") or "").strip() or "[IP 已隐藏]"
    else:
        address = str(
            server.get("original_query")
            or server.get("ip")
            or server.get("hostname")
            or "未知服务器"
        ).strip()

    return format_address_for_pixel_font(address) if pixel_font else address


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
    """是否是合法的 6 位十六进制颜色（不区分大小写，可带 ``#``）。"""
    return bool(re.fullmatch(r"[0-9a-fA-F]{6}", str(color_str or "").strip().lstrip("#")))


def is_valid_api_url(url: str) -> bool:
    """是否是可用作自定义后端的 http(s) 地址。"""
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


__all__ = [
    "is_admin", "is_superuser", "can_manage",
    "is_valid_server_address", "is_valid_hex_color", "is_valid_api_url",
    "format_address_for_pixel_font", "get_server_display_address",
    "BLACKLISTED_PATTERNS",
]
