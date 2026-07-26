"""Minecraft Java 版状态协议（Server List Ping）。

这份实现原先在 ``xducraft_mc_status/status_fetcher.py`` 和
``scripts/mc_status_backend/app.py`` 里各有一份几乎逐字相同的拷贝——
改一处忘另一处只是时间问题。现在只留这一份，两边都引用它。

不用 ``mcstatus`` 直接出结果、而是自己发包的原因：``mcstatus`` 会把状态
JSON 归一化成它自己的对象，丢掉一些服务器自定义的字段；而 MOTD 的颜色渲染
和登录验证方式探测都需要**原始 JSON**。``mcstatus`` 仍然用来做 SRV 解析。
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
from contextlib import suppress
from html import escape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

DEFAULT_SERVER_PORT = 25565
DEFAULT_TIMEOUT = 3.0

#: 状态包的上限。正常 MOTD + favicon 撑死几十 KB，超过这个数多半是恶意响应。
MAX_STATUS_PAYLOAD = 4 * 1024 * 1024


def parse_server_address(address: str, default_port: int = DEFAULT_SERVER_PORT) -> Tuple[str, int]:
    """把 ``host`` / ``host:port`` / ``[v6]:port`` 解析成 ``(主机, 端口)``。"""
    text = str(address or "").strip()
    try:
        parsed = urlparse(f"//{text}")
        hostname = parsed.hostname or text
        port = parsed.port or default_port
    except ValueError:
        # 端口越界等情况下 urlparse 会抛，退回原样 + 默认端口。
        return text, default_port
    return hostname, port


def encode_varint(value: int) -> bytes:
    """编码 Minecraft 协议的 VarInt。"""
    encoded = bytearray()
    if value < 0:
        value = (1 << 32) + value

    while True:
        current = value & 0x7F
        value >>= 7
        if value:
            current |= 0x80
        encoded.append(current)
        if not value:
            break
    return bytes(encoded)


async def read_varint(reader: asyncio.StreamReader) -> int:
    """从流里读一个 VarInt。"""
    num_read = 0
    result = 0

    while True:
        current = (await reader.readexactly(1))[0]
        result |= (current & 0x7F) << (7 * num_read)
        num_read += 1

        if num_read > 5:
            raise ValueError("VarInt 过长")
        if (current & 0x80) == 0:
            break

    if result & (1 << 31):
        result -= 1 << 32
    return result


async def fetch_raw_status(
    connect_host: str,
    connect_port: int,
    handshake_host: str,
    handshake_port: int,
    timeout: float = DEFAULT_TIMEOUT,
) -> Tuple[Dict[str, Any], int]:
    """握手 + 请求状态，返回 ``(原始状态 JSON, 延迟毫秒)``。

    ``handshake_*`` 与 ``connect_*`` 分开传是必要的：走 SRV 记录或反向代理时，
    真正要连的地址和握手里要声明的地址不是同一个，很多服务器（尤其是
    BungeeCord/Velocity 前置）会依据握手里的域名返回不同的 MOTD。
    """
    started_at = time.perf_counter()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(connect_host, connect_port), timeout=timeout
    )

    try:
        host_bytes = handshake_host.encode("utf-8")
        handshake_packet = (
            encode_varint(0)                 # packet id: handshake
            + encode_varint(-1)              # protocol version: -1 = 未指定
            + encode_varint(len(host_bytes)) + host_bytes
            + struct.pack(">H", handshake_port)
            + encode_varint(1)               # next state: status
        )
        writer.write(encode_varint(len(handshake_packet)) + handshake_packet)

        request_packet = encode_varint(0)
        writer.write(encode_varint(len(request_packet)) + request_packet)
        await asyncio.wait_for(writer.drain(), timeout=timeout)

        packet_length = await asyncio.wait_for(read_varint(reader), timeout=timeout)
        if packet_length <= 0 or packet_length > MAX_STATUS_PAYLOAD + 16:
            raise ValueError(f"状态整包长度异常: {packet_length}")

        packet_id = await asyncio.wait_for(read_varint(reader), timeout=timeout)
        if packet_id != 0:
            raise ValueError(f"意外的状态包 ID: {packet_id}")

        payload_length = await asyncio.wait_for(read_varint(reader), timeout=timeout)
        if (
            payload_length < 0
            or payload_length > MAX_STATUS_PAYLOAD
            or payload_length > packet_length
        ):
            raise ValueError(f"状态包长度异常: {payload_length}")

        payload = await asyncio.wait_for(reader.readexactly(payload_length), timeout=timeout)
        latency = int(round((time.perf_counter() - started_at) * 1000))

        status = json.loads(payload.decode("utf-8", errors="replace"))
        if not isinstance(status, dict):
            raise ValueError("状态响应不是 JSON 对象")
        return status, latency
    finally:
        writer.close()
        with suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)


# --- 文本组件（MOTD）转换 ---

def component_to_plain_text(component: Any, _depth: int = 0) -> str:
    """把 Minecraft 文本组件递归转成纯文本。"""
    if component is None or _depth > 32:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, list):
        return "".join(component_to_plain_text(item, _depth + 1) for item in component)
    if isinstance(component, dict):
        text = str(component.get("text", ""))
        return text + component_to_plain_text(component.get("extra", []), _depth + 1)
    return str(component)


def component_to_html(component: Any, inherited_color: Optional[str] = None, _depth: int = 0) -> str:
    """把文本组件转成渲染器认识的 ``<font color=...>`` 片段。"""
    if component is None or _depth > 32:
        return ""
    if isinstance(component, str):
        return escape(component, quote=True).replace("\n", "<br>")
    if isinstance(component, list):
        return "".join(component_to_html(item, inherited_color, _depth + 1) for item in component)
    if isinstance(component, dict):
        current_color = component.get("color") or inherited_color
        text = escape(str(component.get("text", "")), quote=True).replace("\n", "<br>")
        if current_color and text:
            text = f'<font color="{escape(str(current_color), quote=True)}">{text}</font>'
        return text + component_to_html(component.get("extra", []), current_color, _depth + 1)
    return escape(str(component), quote=True).replace("\n", "<br>")


def normalize_description(raw_description: Any) -> Dict[str, str]:
    """把 description 归一化成 ``{"html": ..., "text": ...}``。"""
    normalized: Dict[str, str] = {}
    html = component_to_html(raw_description)
    text = component_to_plain_text(raw_description)
    if html:
        normalized["html"] = html
    if text:
        normalized["text"] = text
    return normalized


def normalize_player_sample(sample: Any, limit: int = 64) -> List[Dict[str, str]]:
    """归一化玩家样本，兼容 dict 与对象两种形态。"""
    if not isinstance(sample, (list, tuple)):
        return []

    normalized: List[Dict[str, str]] = []
    for player in sample:
        if isinstance(player, dict):
            name = player.get("name")
            player_id = player.get("id")
        else:
            name = getattr(player, "name", None)
            player_id = getattr(player, "id", None)

        if not name:
            continue

        entry = {"name": str(name)}
        if player_id is not None:
            entry["id"] = str(player_id)
        normalized.append(entry)

        if len(normalized) >= limit:
            break

    return normalized


async def resolve_connection_candidates(address: str, timeout: float = DEFAULT_TIMEOUT) -> List[Tuple[str, int]]:
    """列出可尝试的 ``(主机, 端口)``：先 SRV 解析结果，再直连地址。"""
    hostname, port = parse_server_address(address)
    candidates: List[Tuple[str, int]] = []

    try:
        from mcstatus import JavaServer

        server = await JavaServer.async_lookup(address, timeout=timeout)
        candidates.append((server.address.host, server.address.port))
    except Exception:
        # SRV 解析失败很常见（大多数服务器没有 SRV 记录），直接走直连。
        pass

    direct = (hostname, port)
    if direct not in candidates:
        candidates.append(direct)
    return candidates


async def query_status(address: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """查询一台服务器，返回**统一结构**的结果。

    永远不抛异常：失败时返回 ``online=False`` 且带 ``error``。
    """
    hostname, port = parse_server_address(address)
    result: Dict[str, Any] = {
        "online": False,
        "hostname": hostname,
        "port": port,
        "original_query": address,
        "ip": address,
    }

    attempt_errors: List[str] = []
    for connect_host, connect_port in await resolve_connection_candidates(address, timeout):
        try:
            raw_status, latency = await fetch_raw_status(
                connect_host=connect_host,
                connect_port=connect_port,
                handshake_host=hostname,
                handshake_port=port,
                timeout=timeout,
            )
        except Exception as exc:
            attempt_errors.append(f"{connect_host}:{connect_port} -> {type(exc).__name__}: {exc}")
            continue

        players = raw_status.get("players") if isinstance(raw_status.get("players"), dict) else {}
        version = raw_status.get("version") if isinstance(raw_status.get("version"), dict) else {}

        result.update({
            "online": True,
            "hostname": connect_host,
            "port": connect_port,
            "ping": latency,
            "version": version.get("name", "N/A") if version else "N/A",
            "protocol": version.get("protocol") if version else None,
            "players": {
                "online": players.get("online", 0),
                "max": players.get("max", 0),
                "sample": normalize_player_sample(players.get("sample")),
            },
        })

        raw_description = raw_status.get("description")
        if raw_description is not None:
            result["description_raw"] = raw_description
            description = normalize_description(raw_description)
            if description:
                result["description"] = description

        favicon = raw_status.get("favicon")
        if favicon:
            result["favicon"] = favicon

        # 1.19.1+ 才有；能拿到就顺手带上，作为验证方式的旁证。
        if "enforcesSecureChat" in raw_status:
            result["enforces_secure_chat"] = bool(raw_status.get("enforcesSecureChat"))

        return result

    result["error"] = "; ".join(attempt_errors) if attempt_errors else "状态查询失败"
    return result


__all__ = [
    "DEFAULT_SERVER_PORT", "DEFAULT_TIMEOUT", "MAX_STATUS_PAYLOAD",
    "parse_server_address", "encode_varint", "read_varint", "fetch_raw_status",
    "component_to_plain_text", "component_to_html", "normalize_description",
    "normalize_player_sample", "resolve_connection_candidates", "query_status",
]
