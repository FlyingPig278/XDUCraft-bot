"""Independent per-group MC status configuration storage."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.config_store import ConfigDocumentStore
from xducraft_bot.shared.data_paths import plugin_data_dir
from xducraft_bot.shared.json_store import as_bool, as_str

from .auth_mode import CONFIGURABLE_MODES
from .constants import DEFAULT_SERVER_PRIORITY, LEGACY_DATA_PATH

DATA_DIR = str(plugin_data_dir(
    "mc_status",
    os.path.join(os.path.dirname(__file__), "data"),
    legacy_relative_path=LEGACY_DATA_PATH,
))
DATA_FILE = os.path.join(DATA_DIR, "server_data.json")
SCHEMA_VERSION_KEY = "__schema_version__"

#: 允许的状态查询源。``auto`` 会按 protocol -> custom -> jsu -> sjtu 依次回退，
#: ``auto_api_first`` 按反向顺序回退（公共 API 优先，protocol 最后兜底）。
VALID_API_SOURCES = frozenset({"protocol", "sjtu", "jsu", "custom", "auto", "auto_api_first"})

#: 全局默认查询源。``auto`` 最稳：本机直连不通时会自动换成公共 API。
DEFAULT_API_SOURCE = "auto"

#: 可以通过 ``/mcs set`` 修改的服务器属性及其默认值（也是 ``/mcs clear`` 的重置目标）。
SERVER_ATTRIBUTE_DEFAULTS: Dict[str, Any] = {
    "tag": "",
    "tag_color": "",
    "comment": "",
    "display_name": "",
    "auth_mode": "",
    "hide_ip": False,
    "ignore_in_list": False,
    "priority": DEFAULT_SERVER_PRIORITY,
}


def _default_group_data() -> Dict[str, Any]:
    return {
        "servers": [],
        "footer": "",
        "show_offline_by_default": False,
        "status_api_source": DEFAULT_API_SOURCE,
        "status_api_url": "",
        "default_auth_mode": "",
        "auth_detect": False,
        "quiet_admin_replies": True,
    }


def _default_data() -> Dict[str, Any]:
    return {SCHEMA_VERSION_KEY: 2}


def _normalize_source(value: Any, fallback: str = "") -> str:
    text = as_str(value).lower()
    return text if text in VALID_API_SOURCES else fallback


def _normalize_auth_mode(value: Any) -> str:
    text = as_str(value).lower()
    return text if text in CONFIGURABLE_MODES else ""


def _normalize_data(raw: Any) -> Dict[str, Any]:
    """Normalize legacy inherited query settings into direct group values."""
    if not isinstance(raw, dict):
        return _default_data()

    data: Dict[str, Any] = _default_data()
    legacy = raw.get(SCHEMA_VERSION_KEY) != 2
    global_raw = raw.get("__global__")
    global_raw = global_raw if isinstance(global_raw, dict) else {}
    legacy_source = _normalize_source(global_raw.get("status_api_source"), DEFAULT_API_SOURCE)
    legacy_url = as_str(global_raw.get("status_api_url"))
    known_groups = set(feature_gate.list_configured_groups()) if legacy else set()

    for key, value in raw.items():
        if key in {"__global__", SCHEMA_VERSION_KEY} or not isinstance(value, dict):
            continue
        try:
            gid = int(key)
        except (TypeError, ValueError):
            continue
        if gid <= 0:
            continue
        known_groups.add(gid)

        group = _default_group_data()
        group["servers"] = _normalize_server_tree(value.get("servers"))
        group["footer"] = as_str(value.get("footer"))
        group["show_offline_by_default"] = as_bool(value.get("show_offline_by_default"), False)
        group["status_api_source"] = _normalize_source(
            value.get("status_api_source"),
            legacy_source if legacy else DEFAULT_API_SOURCE,
        )
        if legacy and not _normalize_source(value.get("status_api_source"), ""):
            group["status_api_source"] = legacy_source
        group["status_api_url"] = as_str(value.get("status_api_url"))
        if legacy and not group["status_api_url"]:
            group["status_api_url"] = legacy_url
        group["default_auth_mode"] = _normalize_auth_mode(value.get("default_auth_mode"))
        group["auth_detect"] = as_bool(value.get("auth_detect"), False)
        group["quiet_admin_replies"] = as_bool(value.get("quiet_admin_replies"), True)
        data[str(gid)] = group
    if legacy:
        for gid in known_groups:
            if str(gid) not in data:
                group = _default_group_data()
                group["status_api_source"] = legacy_source
                group["status_api_url"] = legacy_url
                data[str(gid)] = group
    return data


def _normalize_server_tree(nodes: Any, _depth: int = 0) -> List[Dict[str, Any]]:
    """递归归一化服务器树。

    限制递归深度是为了挡住导入数据里的畸形深树（以及自引用造成的爆栈）。
    """
    if not isinstance(nodes, list) or _depth > 12:
        return []

    normalized: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ip = as_str(node.get("ip"))
        if not ip:
            continue

        entry: Dict[str, Any] = {
            "ip": ip,
            "comment": as_str(node.get("comment")),
            "tag": as_str(node.get("tag")),
            "tag_color": as_str(node.get("tag_color")),
            "ignore_in_list": as_bool(node.get("ignore_in_list"), False),
            "hide_ip": as_bool(node.get("hide_ip"), False),
            "display_name": as_str(node.get("display_name")),
            "auth_mode": _normalize_auth_mode(node.get("auth_mode")),
            "children": _normalize_server_tree(node.get("children"), _depth + 1),
        }

        # priority 是可选的：只有显式配置过才写进去，避免给每台服务器都塞一个默认值。
        if node.get("priority") is not None:
            try:
                entry["priority"] = int(node["priority"])
            except (TypeError, ValueError):
                pass

        normalized.append(entry)

    return normalized


_store = ConfigDocumentStore(
    "mc_status", _default_data, _normalize_data, legacy_path=DATA_FILE,
)


def migrate_legacy_config() -> Dict[str, Any]:
    """Eagerly establish the one-way legacy JSON import at process startup."""
    return _store.load()


def configure_storage(database_path: str, *, legacy_path: Optional[str] = None) -> None:
    """注入隔离配置数据库；旧 JSON 只允许用作首次导入来源。"""
    global _store
    _store = ConfigDocumentStore(
        "mc_status", _default_data,
        _normalize_data, database_path=database_path, legacy_path=legacy_path,
    )


# --- 内部访问器 ---

def _group(data: Dict[str, Any], group_id: int) -> Dict[str, Any]:
    """取某个群的配置块，不存在就地建一个（调用方负责决定要不要保存）。"""
    key = str(group_id)
    existing = data.get(key)
    if not isinstance(existing, dict):
        existing = _default_group_data()
        data[key] = existing
    return existing




def _set_group_field(group_id: int, field: str, value: Any) -> bool:
    """写一个群级字段，返回是否发生变化。"""
    def mutate(data: Dict[str, Any]) -> bool:
        group = _group(data, group_id)
        if group.get(field) == value:
            return False
        group[field] = value
        return True

    return bool(_store.mutate(mutate))




def _get_group_field(group_id: int, field: str, default: Any = None) -> Any:
    data = _store.load()
    group = data.get(str(group_id))
    if not isinstance(group, dict):
        return default
    return group.get(field, default)




# --- 树形结构辅助 ---

def _find_server_in_tree(
    server_tree: List[Dict[str, Any]], server_ip: str
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """在树中按 IP 递归查找，返回 (节点, 所在的兄弟列表)。"""
    for server in server_tree:
        if server.get("ip") == server_ip:
            return server, server_tree
        children = server.get("children") or []
        if children:
            found = _find_server_in_tree(children, server_ip)
            if found:
                return found
    return None


def _flatten_tree(server_tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把树摊平成列表（每项去掉 children）。"""
    flat: List[Dict[str, Any]] = []
    for server in server_tree:
        flat.append({key: value for key, value in server.items() if key != "children"})
        children = server.get("children") or []
        if children:
            flat.extend(_flatten_tree(children))
    return flat


# --- 公共 API：服务器 ---

def get_server_list(group_id: int) -> List[Dict[str, Any]]:
    """取某个群的服务器树。"""
    return _get_group_field(group_id, "servers", []) or []


def get_all_servers_flat(group_id: int) -> List[Dict[str, Any]]:
    """取某个群所有服务器的扁平列表（用于并发查询状态）。"""
    return _flatten_tree(get_server_list(group_id))


def get_server_info(group_id: int, server_ip: str) -> Optional[Dict[str, Any]]:
    """取单台服务器的完整配置。"""
    found = _find_server_in_tree(get_server_list(group_id), server_ip)
    return found[0] if found else None


def add_server(
    group_id: int,
    server_ip: str,
    tag: str = "",
    tag_color: str = "",
    comment: str = "",
    ignore_in_list: bool = False,
    hide_ip: bool = False,
    display_name: str = "",
    parent_ip: str = "",
    priority: int = DEFAULT_SERVER_PRIORITY,
    auth_mode: str = "",
) -> bool:
    """往树里加一台服务器。IP 已存在则返回 False。"""
    def mutate(data: Dict[str, Any]) -> bool:
        group = _group(data, group_id)
        tree = group.setdefault("servers", [])

        if _find_server_in_tree(tree, server_ip):
            return False

        new_server = {
            "ip": server_ip,
            "comment": comment,
            "tag": tag,
            "tag_color": tag_color,
            "ignore_in_list": ignore_in_list,
            "hide_ip": hide_ip,
            "display_name": display_name,
            "auth_mode": _normalize_auth_mode(auth_mode),
            "priority": priority,
            "children": [],
        }

        if parent_ip:
            found = _find_server_in_tree(tree, parent_ip)
            if found:
                found[0].setdefault("children", []).append(new_server)
                return True
        tree.append(new_server)
        return True

    return bool(_store.mutate(mutate))


def remove_server(group_id: int, server_ip: str) -> bool:
    """移除一台服务器及其所有子节点。"""
    def mutate(data: Dict[str, Any]) -> bool:
        group = data.get(str(group_id))
        if not isinstance(group, dict):
            return False
        found = _find_server_in_tree(group.get("servers") or [], server_ip)
        if not found:
            return False
        node, siblings = found
        siblings.remove(node)
        return True

    return bool(_store.mutate(mutate))


def set_server_attribute(group_id: int, server_ip: str, attribute: str, value: Any) -> bool:
    """设置某台服务器的属性。IP 不可改。"""
    if attribute == "ip":
        return False

    if attribute == "auth_mode":
        value = _normalize_auth_mode(value)

    def mutate(data: Dict[str, Any]) -> bool:
        group = data.get(str(group_id))
        if not isinstance(group, dict):
            return False
        found = _find_server_in_tree(group.get("servers") or [], server_ip)
        if not found:
            return False
        found[0][attribute] = value
        return True

    return bool(_store.mutate(mutate))


def clear_server_attribute(group_id: int, server_ip: str, attribute: str) -> bool:
    """把某个属性重置为默认值。"""
    if attribute not in SERVER_ATTRIBUTE_DEFAULTS:
        return False
    return set_server_attribute(group_id, server_ip, attribute, SERVER_ATTRIBUTE_DEFAULTS[attribute])


# --- 公共 API：群级设置 ---

def get_footer(group_id: int) -> str:
    return as_str(_get_group_field(group_id, "footer", ""))


def add_footer(group_id: int, footer_text: str) -> bool:
    return _set_group_field(group_id, "footer", as_str(footer_text))


def clear_footer(group_id: int) -> bool:
    return add_footer(group_id, "")


def get_show_offline_by_default(group_id: int) -> bool:
    return as_bool(_get_group_field(group_id, "show_offline_by_default", False), False)


def set_show_offline_by_default(group_id: int, enabled: bool) -> bool:
    return _set_group_field(group_id, "show_offline_by_default", bool(enabled))


def get_auth_detect_enabled(group_id: int) -> bool:
    """本群是否启用登录验证方式的自动探测。"""
    return as_bool(_get_group_field(group_id, "auth_detect", False), False)


def set_auth_detect_enabled(group_id: int, enabled: bool) -> bool:
    return _set_group_field(group_id, "auth_detect", bool(enabled))


def get_group_default_auth_mode(group_id: int) -> str:
    """本群的默认登录验证方式（未单独配置的服务器会继承它）。"""
    return _normalize_auth_mode(_get_group_field(group_id, "default_auth_mode", ""))


def set_group_default_auth_mode(group_id: int, mode: str) -> bool:
    return _set_group_field(group_id, "default_auth_mode", _normalize_auth_mode(mode))


def get_quiet_admin_replies(group_id: int) -> bool:
    """管理类指令的回执是否走私聊。"""
    return as_bool(_get_group_field(group_id, "quiet_admin_replies", True), True)


def set_quiet_admin_replies(group_id: int, enabled: bool) -> bool:
    return _set_group_field(group_id, "quiet_admin_replies", bool(enabled))


# --- 公共 API：状态查询源 ---

def get_group_status_api_source(group_id: int) -> str:
    """Return this group's direct query source."""
    return _normalize_source(
        _get_group_field(group_id, "status_api_source", DEFAULT_API_SOURCE),
        DEFAULT_API_SOURCE,
    )


def set_group_status_api_source(group_id: int, api_source: str) -> bool:
    normalized = _normalize_source(api_source)
    if not normalized:
        return False
    return _set_group_field(group_id, "status_api_source", normalized)


def clear_group_status_api_source(group_id: int) -> bool:
    return _set_group_field(group_id, "status_api_source", DEFAULT_API_SOURCE)


# --- 公共 API：自定义 API URL ---

def get_group_status_api_url(group_id: int) -> str:
    return as_str(_get_group_field(group_id, "status_api_url", ""))


def set_group_status_api_url(group_id: int, api_url: str) -> bool:
    return _set_group_field(group_id, "status_api_url", as_str(api_url))


def clear_group_status_api_url(group_id: int) -> bool:
    return _set_group_field(group_id, "status_api_url", "")


# --- 公共 API：导入导出 ---

#: 导入时如果 payload 里没有这些键，就**保留现有值**而不是重置。
#: Web UI 的紧凑格式只携带 servers/footer，早期实现会顺手把查询源和 API URL
#: 清空——管理员点一次 /mcs edit 再导入，群里的数据源配置就没了。
_PRESERVE_IF_ABSENT = (
    "status_api_source",
    "status_api_url",
    "default_auth_mode",
    "auth_detect",
    "quiet_admin_replies",
    "show_offline_by_default",
)


def import_group_data(group_id: int, data_to_import: Dict[str, Any]) -> bool:
    """导入并覆盖某个群的配置。

    只有 payload 里**确实带了**的键才会被覆盖，其余保持原值。
    """
    if not isinstance(data_to_import, dict):
        return False
    if not isinstance(data_to_import.get("servers"), list):
        return False

    def mutate(data: Dict[str, Any]) -> bool:
        group = _group(data, group_id)
        group["servers"] = _normalize_server_tree(data_to_import.get("servers"))

        if "footer" in data_to_import:
            group["footer"] = as_str(data_to_import.get("footer"))

        for field in _PRESERVE_IF_ABSENT:
            if field not in data_to_import:
                continue
            value = data_to_import[field]
            if field == "status_api_source":
                group[field] = _normalize_source(value, "")
            elif field == "status_api_url":
                group[field] = as_str(value)
            elif field == "default_auth_mode":
                group[field] = _normalize_auth_mode(value)
            else:
                group[field] = as_bool(value, bool(_default_group_data()[field]))
        return True

    return bool(_store.mutate(mutate))


def export_group_data(group_id: int) -> Dict[str, Any]:
    """导出某个群的完整配置（群不存在时返回默认结构）。"""
    data = _store.load()
    group = data.get(str(group_id))
    if not isinstance(group, dict):
        return _default_group_data()
    return group

def list_configured_groups() -> List[int]:
    """List groups with a stored configuration block."""
    groups: List[int] = []
    for key in _store.load():
        if key == SCHEMA_VERSION_KEY:
            continue
        try:
            group_id = int(key)
        except (TypeError, ValueError):
            continue
        if group_id > 0:
            groups.append(group_id)
    return sorted(set(groups))





__all__ = [
    "DATA_DIR", "DATA_FILE", "SCHEMA_VERSION_KEY", "VALID_API_SOURCES", "DEFAULT_API_SOURCE",
    "SERVER_ATTRIBUTE_DEFAULTS", "configure_storage",
    "get_server_list", "get_all_servers_flat", "get_server_info",
    "add_server", "remove_server", "set_server_attribute", "clear_server_attribute",
    "get_footer", "add_footer", "clear_footer",
    "get_show_offline_by_default", "set_show_offline_by_default",
    "get_auth_detect_enabled", "set_auth_detect_enabled",
    "get_group_default_auth_mode", "set_group_default_auth_mode",
    "get_quiet_admin_replies", "set_quiet_admin_replies",
    "get_group_status_api_source", "set_group_status_api_source", "clear_group_status_api_source",
    "get_group_status_api_url", "set_group_status_api_url", "clear_group_status_api_url",
    "import_group_data", "export_group_data", "list_configured_groups",
]
