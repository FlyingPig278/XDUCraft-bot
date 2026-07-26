"""从各个数据源获取 Minecraft 服务器状态。

四个数据源：

- ``protocol``：本机直连，走 Java 版状态协议。信息最全（含玩家样本 UUID，
  验证方式探测就靠它），但要求机器人所在网络能连上服务器。
- ``jsu`` / ``sjtu``：公共聚合 API，机器人连不上服务器时的兜底。
- ``custom``：自建后端（见 ``scripts/mc_status_backend``）。
- ``auto``：按 protocol → custom → jsu → sjtu 依次回退，任一在线即返回。

**所有数据源的返回值都会过一遍 :func:`sanitize_status`。**
外部 API 返回什么类型完全不由我们决定——``players`` 可能是 ``null``、``ping``
可能是字符串、``sample`` 里可能没有 ``name``。以前这些脏数据会一路流到 Pillow
绘图函数里，然后整条指令以 ``TypeError`` 结束、用户只看到一句“查询失败”。
现在在入口就统一成确定的结构。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import httpx
from nonebot.log import logger

from xducraft_bot.shared import mc_protocol
from xducraft_bot.shared.json_store import as_bool

from . import auth_mode, data_manager
from .constants import DEFAULT_SERVER_PRIORITY

DEFAULT_SERVER_PORT = mc_protocol.DEFAULT_SERVER_PORT
STATUS_QUERY_TIMEOUT = 3.0
SJTU_STATUS_API_URL = "https://mc.sjtu.cn/custom/serverlist/"
JSU_STATUS_API_URL = "https://api.jsumc.fun/ping"

#: 玩家样本最多渲染这么多个，防止某些服务器塞几百个假名字把图撑爆。
MAX_RENDERED_SAMPLE = 32
#: 单条文本字段的长度上限，挡住超长 MOTD / 版本号。
MAX_TEXT_FIELD = 512

_TLS_ERROR_KEYWORDS = (
    "certificate verify failed",
    "certificateverifyfailed",
    "self signed certificate",
    "unable to get local issuer certificate",
    "ssl: cert",
)


# ==============================================================================
# 归一化
# ==============================================================================

def _clamp_text(value: Any, limit: int = MAX_TEXT_FIELD) -> str:
    text = str(value if value is not None else "")
    return text[:limit]


def _coerce_int(value: Any, default: int = 0, *, minimum: int = 0, maximum: int = 10 ** 9) -> int:
    """把任意值转成合理范围内的 int。

    外部 API 见过的实际返回：``"12"``、``12.0``、``null``、``-1``、``1e9``。
    """
    try:
        if isinstance(value, bool):
            raise TypeError
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _sanitize_players(raw: Any) -> Dict[str, Any]:
    """把 players 归一化成 ``{"online": int, "max": int, "sample": [...]}``。"""
    source = raw if isinstance(raw, dict) else {}
    sample = mc_protocol.normalize_player_sample(source.get("sample"), limit=MAX_RENDERED_SAMPLE)
    return {
        "online": _coerce_int(source.get("online"), 0),
        "max": _coerce_int(source.get("max"), 0),
        "sample": [
            {"name": _clamp_text(entry.get("name"), 64), **({"id": entry["id"]} if entry.get("id") else {})}
            for entry in sample
        ],
    }


def _sanitize_version(raw: Any) -> str:
    """版本号可能是 str、``{"name": ...}``，也可能是 None。"""
    if isinstance(raw, dict):
        return _clamp_text(raw.get("name", "N/A"), 128)
    if raw is None:
        return "N/A"
    return _clamp_text(raw, 128)


def _sanitize_description(raw: Any) -> Any:
    """description 保持 dict / str 两种渲染器认识的形态。"""
    def clamp_normalized(value: Dict[str, Any]) -> Optional[Dict[str, str]]:
        result: Dict[str, str] = {}
        if value.get("html"):
            result["html"] = _clamp_text(value["html"], MAX_TEXT_FIELD * 4)
        if value.get("text"):
            result["text"] = _clamp_text(value["text"], MAX_TEXT_FIELD)
        return result or None

    if isinstance(raw, dict):
        result = clamp_normalized(raw)
        # API 直接回了一个文本组件而不是我们的 {html,text} 结构。
        if not result:
            normalized = mc_protocol.normalize_description(raw)
            return clamp_normalized(normalized)
        return result
    if isinstance(raw, list):
        return clamp_normalized(mc_protocol.normalize_description(raw))
    if isinstance(raw, str):
        return _clamp_text(raw, MAX_TEXT_FIELD)
    return None


def sanitize_status(raw: Any, *, ip: str) -> Dict[str, Any]:
    """把任意数据源的返回值收敛成渲染器可以无条件信任的结构。"""
    source = raw if isinstance(raw, dict) else {}
    hostname, port = mc_protocol.parse_server_address(ip)

    result: Dict[str, Any] = {
        "online": as_bool(source.get("online"), False),
        "ip": ip,
        "original_query": _clamp_text(source.get("original_query") or ip, 256),
        "hostname": _clamp_text(source.get("hostname") or hostname, 256),
        "port": _coerce_int(source.get("port"), port, minimum=0, maximum=65535),
    }

    if source.get("error"):
        result["error"] = _clamp_text(source["error"], MAX_TEXT_FIELD)

    if not result["online"]:
        return result

    result["ping"] = _coerce_int(source.get("ping"), 0, maximum=600_000)
    result["version"] = _sanitize_version(source.get("version"))
    result["players"] = _sanitize_players(source.get("players"))

    description = _sanitize_description(source.get("description"))
    if description:
        result["description"] = description

    for optional_key in ("favicon", "protocol", "tls_verify_bypassed", "enforces_secure_chat"):
        if source.get(optional_key) is not None:
            result[optional_key] = source[optional_key]

    if source.get("source"):
        result["source"] = _clamp_text(source["source"], 32)

    return result


def _offline_result(ip: str, error: str, source: str) -> Dict[str, Any]:
    hostname, port = mc_protocol.parse_server_address(ip)
    return {
        "online": False,
        "hostname": hostname,
        "port": port,
        "original_query": ip,
        "ip": ip,
        "error": _clamp_text(error, MAX_TEXT_FIELD),
        "source": source,
    }


# ==============================================================================
# 各数据源
# ==============================================================================

async def _fetch_via_protocol(ip: str) -> Dict[str, Any]:
    """本机直连。"""
    try:
        raw = await mc_protocol.query_status(ip, timeout=STATUS_QUERY_TIMEOUT)
    except Exception as exc:  # query_status 自己不抛，这里只是最后一道保险
        return _offline_result(ip, str(exc), "protocol")
    raw["source"] = "protocol"
    return sanitize_status(raw, ip=ip)


async def _fetch_via_sjtu(ip: str) -> Dict[str, Any]:
    """SJTU 聚合 API。返回结构本身就接近我们的格式。"""
    try:
        async with httpx.AsyncClient(timeout=STATUS_QUERY_TIMEOUT) as client:
            response = await client.get(SJTU_STATUS_API_URL, params={"query": ip})
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("SJTU API 返回格式异常")
        data["source"] = "sjtu"
        return sanitize_status(data, ip=ip)
    except Exception as exc:
        return _offline_result(ip, str(exc), "sjtu")


async def _fetch_via_jsu(ip: str) -> Dict[str, Any]:
    """JSU API。数据包在 ``info`` 里，需要自己拆一层。"""
    try:
        async with httpx.AsyncClient(timeout=STATUS_QUERY_TIMEOUT) as client:
            response = await client.get(JSU_STATUS_API_URL, params={"server": ip})
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise ValueError("JSU API 返回格式异常")
        info = data.get("info")
        if not isinstance(info, dict):
            raise ValueError("JSU API 缺少 info 字段")

        target = str(data.get("target", "") or "").strip()
        hostname, port = mc_protocol.parse_server_address(target or ip)

        merged = {
            "online": True,
            "hostname": hostname,
            "port": port,
            "original_query": ip,
            "ip": ip,
            "ping": data.get("latency", 0),
            "version": info.get("version"),
            "players": info.get("players"),
            "description": info.get("description"),
            "favicon": info.get("favicon"),
            "source": "jsu",
        }
        version = info.get("version")
        if isinstance(version, dict):
            merged["protocol"] = version.get("protocol")
        return sanitize_status(merged, ip=ip)
    except Exception as exc:
        return _offline_result(ip, str(exc), "jsu")


def _is_tls_verification_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(keyword in text for keyword in _TLS_ERROR_KEYWORDS)


async def _request_custom(ip: str, api_url: str, verify_tls: bool) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=STATUS_QUERY_TIMEOUT, verify=verify_tls) as client:
        response = await client.get(api_url, params={"query": ip})
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("自定义 API 返回格式异常")
    return data


async def _fetch_via_custom(ip: str, api_url: str) -> Dict[str, Any]:
    """自建后端。自签证书时会降级重试一次，并在结果里标注。"""
    normalized_url = str(api_url or "").strip()
    if not normalized_url:
        return _offline_result(ip, "未配置自定义 API URL", "custom")

    try:
        data = await _request_custom(ip, normalized_url, verify_tls=True)
    except Exception as first_error:
        if not _is_tls_verification_error(first_error):
            return _offline_result(ip, str(first_error), "custom")
        try:
            data = await _request_custom(ip, normalized_url, verify_tls=False)
            data["tls_verify_bypassed"] = True
        except Exception as second_error:
            return _offline_result(
                ip,
                f"TLS 校验失败且降级重试未通过: verify=true -> {first_error}; verify=false -> {second_error}",
                "custom",
            )

    data["source"] = "custom"
    return sanitize_status(data, ip=ip)


# ==============================================================================
# 调度
# ==============================================================================

def _is_online(result: Dict[str, Any]) -> bool:
    return bool(result.get("online"))


async def get_single_server_status(ip: str, group_id: Optional[int] = None) -> Dict[str, Any]:
    """按群配置的数据源查询单台服务器。"""
    api_source = data_manager.DEFAULT_API_SOURCE
    custom_api_url = ""
    if group_id is not None:
        api_source = data_manager.get_status_api_source(group_id)
        custom_api_url, _ = data_manager.get_effective_status_api_url(group_id)

    if api_source == "custom":
        return await _fetch_via_custom(ip, custom_api_url)
    if api_source == "jsu":
        return await _fetch_via_jsu(ip)
    if api_source == "sjtu":
        return await _fetch_via_sjtu(ip)
    if api_source == "protocol":
        return await _fetch_via_protocol(ip)

    return await _fetch_with_fallback(ip, custom_api_url)


async def _fetch_with_fallback(ip: str, custom_api_url: str) -> Dict[str, Any]:
    """``auto``：依次尝试各数据源，第一个在线的即返回。

    全部失败时返回 protocol 的结果，但 ``error`` 里会汇总每个源的失败原因，
    方便管理员用 ``/mcs diag`` 定位是网络不通还是服务器真的挂了。
    """
    attempts: List[Tuple[str, Dict[str, Any]]] = []

    protocol_result = await _fetch_via_protocol(ip)
    if _is_online(protocol_result):
        return protocol_result
    attempts.append(("protocol", protocol_result))

    if custom_api_url:
        custom_result = await _fetch_via_custom(ip, custom_api_url)
        if _is_online(custom_result):
            return custom_result
        attempts.append(("custom", custom_result))

    jsu_result = await _fetch_via_jsu(ip)
    if _is_online(jsu_result):
        return jsu_result
    attempts.append(("jsu", jsu_result))

    sjtu_result = await _fetch_via_sjtu(ip)
    if _is_online(sjtu_result):
        return sjtu_result
    attempts.append(("sjtu", sjtu_result))

    summary = "; ".join(
        f"{name}: {result.get('error') or '无错误信息'}" for name, result in attempts
    )
    protocol_result["error"] = _clamp_text(summary, MAX_TEXT_FIELD * 2)
    protocol_result["source"] = "auto"
    return protocol_result


def _merge_results_into_tree(
    server_nodes: List[Dict[str, Any]],
    status_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把状态数据合并回服务器树（不改动入参）。

    合并方向很关键：**用户配置覆盖实时状态**。多线服务器的状态是按解析后的
    单个 IP 查的，但展示时要用用户填的原始地址和标签。
    """
    enriched: List[Dict[str, Any]] = []
    for node in server_nodes:
        ip = node.get("ip", "")
        status = status_map.get(ip) or {
            "online": False,
            "original_query": ip,
            "error": "未找到状态",
        }

        merged = {**status, **{key: value for key, value in node.items() if key != "children"}}
        children = node.get("children") or []
        if children:
            merged["children"] = _merge_results_into_tree(children, status_map)
        enriched.append(merged)
    return enriched


async def get_all_servers_status(group_id: int) -> List[Dict[str, Any]]:
    """查询一个群的全部服务器，返回带状态的树。"""
    server_tree = data_manager.get_server_list(group_id)
    if not server_tree:
        return []

    flat_servers = data_manager.get_all_servers_flat(group_id)
    if not flat_servers:
        return []

    # 同一个 IP 可能在树里出现多次，去重避免重复查询。
    unique_ips = list(dict.fromkeys(server.get("ip", "") for server in flat_servers if server.get("ip")))

    results = await asyncio.gather(
        *(get_single_server_status(ip, group_id=group_id) for ip in unique_ips),
        return_exceptions=True,
    )

    status_map: Dict[str, Dict[str, Any]] = {}
    for ip, result in zip(unique_ips, results):
        if isinstance(result, Exception):
            logger.warning("[MCStatus] 查询 {} 抛出异常: {}", ip, result)
            status_map[ip] = _offline_result(ip, f"{type(result).__name__}: {result}", "unknown")
        else:
            status_map[ip] = result

    merged_tree = _merge_results_into_tree(server_tree, status_map)

    if data_manager.get_auth_detect_enabled(group_id):
        # 探测失败/超时都不影响出图，annotate_servers 内部已经吞掉了所有异常。
        await auth_mode.annotate_servers(merged_tree)

    return merged_tree


# ==============================================================================
# 展示前处理
# ==============================================================================

ANONYMOUS_PLAYER_UUID = "00000000-0000-0000-0000-000000000000"


def preprocess_server_data(server_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去掉匿名占位玩家。返回新结构，不修改入参。"""
    processed: List[Dict[str, Any]] = []
    for node in server_data_list:
        if not isinstance(node, dict):
            continue
        current = dict(node)

        players = current.get("players")
        if current.get("online") and isinstance(players, dict) and players.get("sample"):
            filtered = [
                player for player in players["sample"]
                if isinstance(player, dict) and player.get("id") != ANONYMOUS_PLAYER_UUID
            ]
            current["players"] = {**players, "sample": filtered}

        children = current.get("children")
        if children:
            current["children"] = preprocess_server_data(children)

        processed.append(current)
    return processed


def get_server_display_key(server_info: Dict[str, Any]) -> Tuple:
    """同层排序键。priority 越小越靠前。"""
    try:
        priority = int(server_info.get("priority", DEFAULT_SERVER_PRIORITY))
    except (TypeError, ValueError):
        priority = DEFAULT_SERVER_PRIORITY
    return (priority,)


def prepare_data_for_display(
    server_tree: List[Dict[str, Any]],
    show_all_servers: bool,
) -> List[Dict[str, Any]]:
    """过滤 + 排序，产出最终要画的树。不修改入参。"""
    display_tree: List[Dict[str, Any]] = []
    for node in server_tree:
        if not isinstance(node, dict) or node.get("ignore_in_list"):
            continue

        current = dict(node)
        children = current.get("children")
        if children:
            current["children"] = prepare_data_for_display(children, show_all_servers)

        is_online = bool(current.get("online"))
        has_visible_children = bool(current.get("children"))

        if show_all_servers or is_online or has_visible_children:
            display_tree.append(current)

    # 稳定排序：所有 priority 相同时完全保持 Web UI 里拖拽出来的顺序，
    # 只有显式设过 priority 的服务器才会被提前。
    display_tree.sort(key=get_server_display_key)
    return display_tree


def _iter_nodes(nodes: List[Dict[str, Any]]):
    for node in nodes:
        yield node
        children = node.get("children")
        if children:
            yield from _iter_nodes(children)


def has_player_list(server_data: Dict[str, Any]) -> bool:
    """该服务器是否要额外画一行“正在游玩”。"""
    if not server_data.get("online"):
        return False
    players = server_data.get("players")
    if not isinstance(players, dict):
        return False
    return bool(players.get("online")) and bool(players.get("sample"))


def get_active_server_count(display_data: List[Dict[str, Any]]) -> int:
    """有活跃玩家列表的服务器数量。"""
    return sum(1 for node in _iter_nodes(display_data) if has_player_list(node))


def summarize(display_data: List[Dict[str, Any]]) -> Dict[str, int]:
    """整棵树的汇总数据，用于图片顶部的概览条。"""
    total = online = players_online = players_max = 0
    for node in _iter_nodes(display_data):
        total += 1
        if not node.get("online"):
            continue
        online += 1
        players = node.get("players")
        if isinstance(players, dict):
            players_online += _coerce_int(players.get("online"), 0)
            players_max += _coerce_int(players.get("max"), 0)

    return {
        "total": total,
        "online": online,
        "offline": total - online,
        "players_online": players_online,
        "players_max": players_max,
    }


__all__ = [
    "STATUS_QUERY_TIMEOUT", "SJTU_STATUS_API_URL", "JSU_STATUS_API_URL",
    "sanitize_status", "get_single_server_status", "get_all_servers_status",
    "preprocess_server_data", "prepare_data_for_display", "get_server_display_key",
    "get_active_server_count", "has_player_list", "summarize",
]
