"""``/mcs edit`` 用的配置压缩 / 解压。

配置要塞进一条 QQ 消息里的 URL，而 QQ 对**可点击**链接的长度有上限，超了就
变成不可点的纯文本。所以这里不是随便 base64 一下，而是：

1. 把服务器树转成**位置编码的紧凑数组**（省掉所有 JSON 键名）；
2. 空值一律写成 ``0``（比 ``""`` 短，且 zlib 对重复的 0 压得更狠）；
3. zlib level 9 + URL-safe base64，去掉 ``=`` 填充。

紧凑数组的下标是**和 Vue 前端共享的协议**（见 mcs-editor 的 ``src/App.vue``），
新增字段只能往**后面追加**，并且两端都必须用 ``len(item) > 下标`` 做兼容判断：

- 老前端读新数据：多出来的尾部元素被忽略，功能不变；
- 新后端读老数据：下标越界，回退到默认值。

绝对不要在中间插入下标，那会让所有旧链接错位。
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any, Dict, List, Optional

from nonebot.log import logger

from .auth_mode import code_to_mode, mode_to_code

# --- 紧凑数组下标（与 mcs-editor/src/App.vue 保持一致）---
S_IP = 0
S_COMMENT = 1
S_TAG = 2
S_TAG_COLOR = 3
S_IGNORE = 4
S_HIDE_IP = 5
S_DISPLAY_NAME = 6
S_CHILDREN = 7
S_AUTH_MODE = 8  # 新增：登录验证方式，整数编码，缺省 0 = 未配置

#: 顶层结构下标：[footer, show_offline_by_default, servers]
T_FOOTER = 0
T_SHOW_OFFLINE = 1
T_SERVERS = 2

#: 解压时的防御上限，挡住恶意构造的“压缩炸弹”。
MAX_INFLATED_BYTES = 2 * 1024 * 1024
MAX_TREE_DEPTH = 12


def _item_get(item: List[Any], index: int, default: Any = None) -> Any:
    """按下标安全取值，越界返回默认值（这就是向后兼容的关键）。"""
    if not isinstance(item, list) or len(item) <= index:
        return default
    return item[index]


def _json_to_compact_array(servers: Any, _depth: int = 0) -> List[Any]:
    """服务器树 -> 紧凑数组。空值统一写 0 以压缩体积。"""
    if not isinstance(servers, list) or _depth > MAX_TREE_DEPTH:
        return []

    compact: List[Any] = []
    for server in servers:
        if not isinstance(server, dict):
            continue
        compact.append([
            server.get("ip") or "",
            server.get("comment") or 0,
            server.get("tag") or 0,
            server.get("tag_color") or 0,
            1 if server.get("ignore_in_list") else 0,
            1 if server.get("hide_ip") else 0,
            server.get("display_name") or 0,
            _json_to_compact_array(server.get("children"), _depth + 1) or 0,
            mode_to_code(server.get("auth_mode")),
        ])
    return compact


def _compact_array_to_json(compact_data: Any, _depth: int = 0) -> List[Dict[str, Any]]:
    """紧凑数组 -> 服务器树。"""
    if not isinstance(compact_data, list) or _depth > MAX_TREE_DEPTH:
        return []

    servers: List[Dict[str, Any]] = []
    for item in compact_data:
        if not isinstance(item, list) or not item:
            continue

        ip = _item_get(item, S_IP, "")
        if not ip:
            continue

        children_raw = _item_get(item, S_CHILDREN, [])
        servers.append({
            "ip": str(ip),
            "comment": str(_item_get(item, S_COMMENT, "") or ""),
            "tag": str(_item_get(item, S_TAG, "") or ""),
            "tag_color": str(_item_get(item, S_TAG_COLOR, "") or ""),
            "ignore_in_list": _item_get(item, S_IGNORE, 0) == 1,
            "hide_ip": _item_get(item, S_HIDE_IP, 0) == 1,
            "display_name": str(_item_get(item, S_DISPLAY_NAME, "") or ""),
            "auth_mode": code_to_mode(_item_get(item, S_AUTH_MODE, 0)),
            "children": _compact_array_to_json(children_raw, _depth + 1)
            if isinstance(children_raw, list) else [],
        })
    return servers


def _to_url_safe_base64(raw: bytes) -> str:
    return base64.b64encode(raw).replace(b"+", b"-").replace(b"/", b"_").rstrip(b"=").decode("ascii")


def _from_url_safe_base64(text: str) -> bytes:
    normalized = str(text).strip().replace("-", "+").replace("_", "/")
    padding = -len(normalized) % 4
    return (normalized + "=" * padding).encode("ascii")


def compress_config(group_data: Dict[str, Any]) -> str:
    """把群配置压成 URL 安全的短字符串；失败返回空串。"""
    try:
        compact_structure = [
            group_data.get("footer") or 0,
            1 if group_data.get("show_offline_by_default") else 0,
            _json_to_compact_array(group_data.get("servers")),
        ]
        payload = json.dumps(compact_structure, separators=(",", ":"), ensure_ascii=False)
        compressed = zlib.compress(payload.encode("utf-8"), level=9)
        return _to_url_safe_base64(compressed)
    except Exception as exc:
        logger.error("[ConfigCoder] 压缩配置失败: {}", exc)
        return ""


def decompress_config(encoded_string: str) -> Optional[Dict[str, Any]]:
    """把压缩字符串还原成群配置；任何异常都返回 None。

    注意返回值里**只有** payload 真正携带的键。``import_group_data`` 会据此
    保留未携带的群级设置（查询源、API URL 等），不会把它们清空。
    """
    if not str(encoded_string or "").strip():
        return None

    try:
        binary = base64.b64decode(_from_url_safe_base64(encoded_string), validate=False)
    except Exception as exc:
        logger.info("[ConfigCoder] base64 解码失败: {}", exc)
        return None

    try:
        decompressor = zlib.decompressobj()
        inflated = decompressor.decompress(binary, MAX_INFLATED_BYTES)
        if decompressor.unconsumed_tail:
            logger.warning("[ConfigCoder] 解压结果超过 {} 字节上限，拒绝导入。", MAX_INFLATED_BYTES)
            return None
        if not decompressor.eof or decompressor.unused_data:
            logger.info("[ConfigCoder] 压缩数据不完整或包含多余尾部，拒绝导入。")
            return None
        payload = inflated.decode("utf-8")
    except Exception as exc:
        logger.info("[ConfigCoder] zlib 解压失败: {}", exc)
        return None

    try:
        structure = json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.info("[ConfigCoder] 解压后不是合法 JSON: {}", exc)
        return None

    if not isinstance(structure, list) or len(structure) <= T_SERVERS:
        logger.info("[ConfigCoder] 紧凑结构格式不正确。")
        return None

    return {
        "footer": str(structure[T_FOOTER] or ""),
        "show_offline_by_default": structure[T_SHOW_OFFLINE] == 1,
        "servers": _compact_array_to_json(structure[T_SERVERS]),
    }


__all__ = [
    "compress_config", "decompress_config",
    "S_IP", "S_COMMENT", "S_TAG", "S_TAG_COLOR", "S_IGNORE",
    "S_HIDE_IP", "S_DISPLAY_NAME", "S_CHILDREN", "S_AUTH_MODE",
]
