import asyncio
import json
import struct
import time
from contextlib import suppress
from html import escape
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse

from mcstatus import JavaServer

from . import data_manager
from .constants import DEFAULT_SERVER_PRIORITY


DEFAULT_SERVER_PORT = 25565
STATUS_QUERY_TIMEOUT = 3.0


def _encode_varint(value: int) -> bytes:
    """编码 Minecraft 协议使用的 VarInt。"""
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


async def _read_varint(reader: asyncio.StreamReader) -> int:
    """读取 Minecraft 协议中的 VarInt。"""
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


async def _fetch_raw_status_payload(
    connect_host: str,
    connect_port: int,
    handshake_host: str,
    handshake_port: int,
) -> tuple[dict[str, Any], int]:
    """直接请求 Java 版状态协议，返回原始 JSON 以及延迟。"""
    started_at = time.perf_counter()
    connection = asyncio.open_connection(connect_host, connect_port)
    reader, writer = await asyncio.wait_for(connection, timeout=STATUS_QUERY_TIMEOUT)

    try:
        host_bytes = handshake_host.encode("utf-8")
        handshake_packet = (
            _encode_varint(0) +
            _encode_varint(-1) +
            _encode_varint(len(host_bytes)) + host_bytes +
            struct.pack(">H", handshake_port) +
            _encode_varint(1)
        )
        writer.write(_encode_varint(len(handshake_packet)) + handshake_packet)

        request_packet = _encode_varint(0)
        writer.write(_encode_varint(len(request_packet)) + request_packet)
        await asyncio.wait_for(writer.drain(), timeout=STATUS_QUERY_TIMEOUT)

        await asyncio.wait_for(_read_varint(reader), timeout=STATUS_QUERY_TIMEOUT)
        packet_id = await asyncio.wait_for(_read_varint(reader), timeout=STATUS_QUERY_TIMEOUT)
        if packet_id != 0:
            raise ValueError(f"意外的状态包 ID: {packet_id}")

        payload_length = await asyncio.wait_for(_read_varint(reader), timeout=STATUS_QUERY_TIMEOUT)
        payload = await asyncio.wait_for(reader.readexactly(payload_length), timeout=STATUS_QUERY_TIMEOUT)
        latency = int(round((time.perf_counter() - started_at) * 1000))
        return json.loads(payload.decode("utf-8")), latency
    finally:
        writer.close()
        with suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)


def _parse_server_address(address: str) -> tuple[str, int]:
    """解析服务器地址，并在缺失端口时回退到 Java 版默认端口。"""
    parsed = urlparse(f"//{address}")
    hostname = parsed.hostname or address
    port = parsed.port or DEFAULT_SERVER_PORT
    return hostname, port


def _component_to_plain_text(component: Any) -> str:
    """将 Minecraft 文本组件递归转换为纯文本。"""
    if component is None:
        return ""

    if isinstance(component, str):
        return component

    if isinstance(component, list):
        return "".join(_component_to_plain_text(item) for item in component)

    if isinstance(component, dict):
        text = str(component.get("text", ""))
        extra = _component_to_plain_text(component.get("extra", []))
        return text + extra

    return str(component)


def _component_to_html(component: Any, inherited_color: str | None = None) -> str:
    """将 Minecraft 文本组件递归转换为现有渲染器可识别的 HTML/font 片段。"""
    if component is None:
        return ""

    if isinstance(component, str):
        return escape(component, quote=True).replace("\n", "<br>")

    if isinstance(component, list):
        return "".join(_component_to_html(item, inherited_color) for item in component)

    if isinstance(component, dict):
        current_color = component.get("color") or inherited_color
        text = escape(str(component.get("text", "")), quote=True).replace("\n", "<br>")
        if current_color and text:
            text = f'<font color="{escape(str(current_color), quote=True)}">{text}</font>'
        extra = _component_to_html(component.get("extra", []), current_color)
        return text + extra

    return escape(str(component), quote=True).replace("\n", "<br>")


def _normalize_description(raw_description: Any) -> Dict[str, str]:
    """将 mcstatus 返回的 description 适配为旧渲染器依赖的结构。"""
    text = _component_to_plain_text(raw_description)
    html = _component_to_html(raw_description)

    normalized: Dict[str, str] = {}
    if html:
        normalized["html"] = html
    if text:
        normalized["text"] = text
    return normalized


def _normalize_player_sample(sample: Any) -> List[Dict[str, str]]:
    """统一玩家示例列表的结构，兼容 dict 与对象两种返回形态。"""
    if not sample:
        return []

    normalized_sample: List[Dict[str, str]] = []
    for player in sample:
        if isinstance(player, dict):
            player_name = player.get("name")
            player_id = player.get("id")
        else:
            player_name = getattr(player, "name", None)
            player_id = getattr(player, "id", None)

        if not player_name:
            continue

        normalized_player = {"name": str(player_name)}
        if player_id is not None:
            normalized_player["id"] = str(player_id)
        normalized_sample.append(normalized_player)

    return normalized_sample


async def get_single_server_status(ip: str) -> Dict[str, Any]:
    """通过 Java 版状态协议直接获取单个 Minecraft 服务器的状态。"""
    hostname, port = _parse_server_address(ip)
    fallback_response = {
        "online": False,
        "hostname": hostname,
        "port": port,
        "original_query": ip,
        "ip": ip,
    }

    try:
        connection_candidates: list[tuple[str, int]] = []

        try:
            server = await JavaServer.async_lookup(ip, timeout=STATUS_QUERY_TIMEOUT)
            connection_candidates.append((server.address.host, server.address.port))
        except Exception:
            pass

        direct_target = (hostname, port)
        if direct_target not in connection_candidates:
            connection_candidates.append(direct_target)

        last_error: Exception | None = None
        raw_status: dict[str, Any] | None = None
        latency: int | None = None
        resolved_host_for_output = hostname
        resolved_port_for_output = port

        for connect_host, connect_port in connection_candidates:
            try:
                raw_status, latency = await _fetch_raw_status_payload(
                    connect_host=connect_host,
                    connect_port=connect_port,
                    handshake_host=hostname,
                    handshake_port=port,
                )
                resolved_host_for_output = connect_host
                resolved_port_for_output = connect_port
                break
            except Exception as connect_error:
                last_error = connect_error

        if raw_status is None or latency is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("状态查询失败")

        players = raw_status.get("players", {}) if isinstance(raw_status.get("players"), dict) else {}
        version = raw_status.get("version", {})
        raw_description = raw_status.get("description")

        response_data: Dict[str, Any] = {
            **fallback_response,
            "online": True,
            "hostname": resolved_host_for_output,
            "port": resolved_port_for_output,
            "ping": latency,
            "version": version.get("name", "N/A") if isinstance(version, dict) else str(version),
            "protocol": version.get("protocol") if isinstance(version, dict) else None,
            "players": {
                "online": players.get("online", 0),
                "max": players.get("max", 0),
                "sample": _normalize_player_sample(players.get("sample")),
            },
        }

        if raw_description is not None:
            response_data["description_raw"] = raw_description
            normalized_description = _normalize_description(raw_description)
            if normalized_description:
                response_data["description"] = normalized_description

        favicon = raw_status.get("favicon")
        if favicon:
            response_data["favicon"] = favicon

        return response_data
    except Exception as e:
        fallback_response["error"] = str(e)
        return fallback_response


def _merge_results_into_tree(
    server_nodes: List[Dict[str, Any]],
    status_map: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    递归地遍历服务器树，并将状态数据注入其中。
    """
    enriched_tree = []
    for node in server_nodes:
        ip = node['ip']
        status_data = status_map.get(ip, {"online": False, "original_query": ip, "error": "未找到状态"})

        # 正确处理多线服务器非常重要。
        # 状态API解析的是单个IP，但我们想显示用户原始的查询地址。
        # 原始树节点 (`node`) 持有用户配置的元数据 (tag, comment等)。
        # 状态数据 (`status_data`) 持有实时的查询结果。
        # 我们合并它们，优先使用用户配置的元数据。
        enriched_node = {
            **status_data,  # 实时状态 (在线情况, 玩家, motd等)
            **node,         # 用户配置 (ip, comment, tag等会覆盖状态中的同名字段)
        }

        if 'children' in node and node['children']:
            enriched_node['children'] = _merge_results_into_tree(node['children'], status_map)

        enriched_tree.append(enriched_node)
    return enriched_tree


async def get_all_servers_status(group_id: int) -> List[Dict[str, Any]]:
    """
    获取一个群组所有服务器的状态，并返回一个数据丰富的树形结构。
    """
    # 1. 获取原始的服务器树形结构
    server_tree = data_manager.get_server_list(group_id)
    if not server_tree:
        return []

    # 2. 扁平化树以获取所有用于API调用的唯一IP
    flat_server_list = data_manager.get_all_servers_flat(group_id)
    if not flat_server_list:
        return []

    # 3. 并发获取所有服务器的状态
    tasks = [get_single_server_status(server['ip']) for server in flat_server_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 4. 创建一个从IP到状态结果的映射，便于查找
    status_map: Dict[str, Dict[str, Any]] = {}
    for res in results:
        if not isinstance(res, Exception) and 'original_query' in res:
            status_map[res['original_query']] = res

    # 5. 递归地将状态结果合并回原始的树形结构中
    merged_tree = _merge_results_into_tree(server_tree, status_map)

    return merged_tree


def preprocess_server_data(server_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """递归地处理树，修正玩家数量和处理匿名玩家。"""
    processed_list = []
    for res in server_data_list:
        if res.get('online') and res.get('players', {}).get('sample'):
            valid_players = [
                p for p in res['players']['sample']
                if p.get('id') != '00000000-0000-0000-0000-000000000000'
            ]
            res['players']['sample'] = valid_players

        if 'children' in res and res['children']:
            res['children'] = preprocess_server_data(res['children'])

        processed_list.append(res)
    return processed_list


def get_server_display_key(server_info: Dict[str, Any]) -> Tuple:
    """
    生成一个用于在同一层级对服务器进行排序的元组键。
    优先级是主要的排序键。
    """
    return (
        server_info.get('priority', DEFAULT_SERVER_PRIORITY),
        server_info.get('ip', '')  # 后备，用于稳定排序
    )


def prepare_data_for_display(
    server_tree: List[Dict[str, Any]],
    show_all_servers: bool
) -> List[Dict[str, Any]]:
    """
    递归地过滤和排序服务器树，用于最终渲染。
    """
    display_tree = []
    for node in server_tree:
        # 如果一个服务器被标记为忽略，则跳过它和它的整个分支。
        if node.get('ignore_in_list', False):
            continue

        # 首先，递归地处理子节点
        if 'children' in node and node['children']:
            node['children'] = prepare_data_for_display(node['children'], show_all_servers)

        # 然后，根据在线状态决定当前节点是否应被包含
        is_online = node.get('online', False)
        has_visible_children = bool(node.get('children'))

        if show_all_servers or is_online or has_visible_children:
            display_tree.append(node)

    # 对当前层级的节点进行排序
    # display_tree.sort(key=get_server_display_key)
    return display_tree


def get_active_server_count(display_data: list[dict[str, Any]]) -> int:
    """在显示树中递归地计算拥有活跃玩家列表的服务器数量。"""
    count = 0
    for server_data in display_data:
        if server_data.get('online') and server_data.get('players', {}).get('online') != 0 and server_data.get('players', {}).get('sample'):
            count += 1
        if 'children' in server_data and server_data['children']:
            count += get_active_server_count(server_data['children'])
    return count
