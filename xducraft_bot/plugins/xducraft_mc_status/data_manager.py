import json
import os
from typing import Dict, List, Any, Tuple, Optional

from .constants import DEFAULT_SERVER_PRIORITY

# --- 文件I/O与基础结构 ---

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "server_data.json")


def _load_data() -> dict:
    """从JSON文件中加载所有数据。"""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_data(data: Dict[str, Any]):
    """将所有数据保存到JSON文件。"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _ensure_group_data_exists(data: Dict[str, Any], group_id_str: str):
    """确保一个群组的基础数据结构存在。"""
    data.setdefault(group_id_str, {
        "servers": [],
        "footer": "",
        "show_offline_by_default": False
    })


# --- 树形结构遍历与操作辅助函数 ---

def _find_server_in_tree(
        server_tree: List[Dict[str, Any]], server_ip: str
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    在树中递归地通过IP查找服务器。

    返回:
        一个元组 (服务器字典, 父列表)，如果找到的话，否则返回 None。
        父列表是包含该服务器的列表 (例如，根列表或某个节点的children列表)。
    """
    for server in server_tree:
        if server.get('ip') == server_ip:
            return server, server_tree
        children = server.get('children', [])
        if children:
            found = _find_server_in_tree(children, server_ip)
            if found:
                return found
    return None


def _flatten_tree(server_tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将服务器树扁平化为一个列表。"""
    flat_list = []
    for server in server_tree:
        children = server.get('children', [])
        # 创建一个不包含children的副本以添加到扁平列表
        server_copy = {k: v for k, v in server.items() if k != 'children'}
        flat_list.append(server_copy)
        if children:
            flat_list.extend(_flatten_tree(children))
    return flat_list


# --- 公共API：数据管理 ---


def get_server_list(group_id: int) -> List[Dict[str, Any]]:
    """
    获取一个群组的服务器列表，这是一个树形结构。
    """
    data = _load_data()
    group_id_str = str(group_id)
    return data.get(group_id_str, {}).get("servers", [])


def get_all_servers_flat(group_id: int) -> List[Dict[str, Any]]:
    """
    获取一个群组所有服务器的扁平列表。
    用于需要遍历每个服务器的任务，例如获取状态。
    """
    server_tree = get_server_list(group_id)
    return _flatten_tree(server_tree)


def get_server_info(group_id: int, server_ip: str) -> Optional[Dict[str, Any]]:
    """获取单个服务器的完整信息字典。"""
    server_tree = get_server_list(group_id)
    found = _find_server_in_tree(server_tree, server_ip)
    return found[0] if found else None


def get_show_offline_by_default(group_id: int) -> bool:
    """获取一个群组的 'show_offline_by_default' 标志。"""
    data = _load_data()
    group_id_str = str(group_id)
    return data.get(group_id_str, {}).get("show_offline_by_default", False)


def add_server(group_id: int, server_ip: str, tag: str = "", tag_color: str = "",
               comment: str = "", ignore_in_list: bool = False,
               parent_ip: str = "", priority: int = DEFAULT_SERVER_PRIORITY) -> bool:
    """向树中添加一个服务器。"""
    data = _load_data()
    group_id_str = str(group_id)
    _ensure_group_data_exists(data, group_id_str)
    server_tree = data[group_id_str]["servers"]
    # 检查IP是否已在树中的任何位置存在
    if get_server_info(group_id, server_ip):
        return False

    new_server = {
        "ip": server_ip,
        "comment": comment,
        "tag": tag,
        "tag_color": tag_color,
        "ignore_in_list": ignore_in_list,
        "priority": priority,
        "children": []
        # parent_ip 和 server_type 由结构隐式定义
    }

    if parent_ip:
        # 作为子节点添加
        found = _find_server_in_tree(server_tree, parent_ip)
        if found:
            parent_server, _ = found
            parent_server.setdefault('children', []).append(new_server)
        else:
            # 未找到父节点，作为根节点添加（兜底）
            server_tree.append(new_server)
    else:
        # 添加到根节点
        server_tree.append(new_server)
    _save_data(data)
    return True


def remove_server(group_id: int, server_ip: str) -> bool:
    """从树中移除一个服务器（及其所有后代节点）。"""
    data = _load_data()
    group_id_str = str(group_id)
    if group_id_str not in data:
        return False

    server_tree = data[group_id_str]["servers"]
    found = _find_server_in_tree(server_tree, server_ip)

    if found:
        server_to_remove, parent_list = found
        parent_list.remove(server_to_remove)
        _save_data(data)
        return True

    return False


def set_server_attribute(group_id: int, server_ip: str, attribute: str, value: Any) -> bool:
    """在树中为特定服务器设置一个属性。"""
    if attribute == 'ip':
        return False  # IP不应通过此方式修改

    data = _load_data()
    group_id_str = str(group_id)
    if group_id_str not in data:
        return False

    server_tree = data[group_id_str]["servers"]
    found = _find_server_in_tree(server_tree, server_ip)

    if found:
        server, _ = found
        server[attribute] = value
        _save_data(data)
        return True

    return False


def clear_server_attribute(group_id: int, server_ip: str, attribute: str) -> bool:
    """清空服务器的某个属性，将其设为默认值。"""
    if attribute in ['ip']:
        return False

    default_values = {
        'tag': '',
        'tag_color': '',
        'comment': '',
        'priority': DEFAULT_SERVER_PRIORITY,
        'ignore_in_list': False
    }

    if attribute not in default_values:
        return False

    return set_server_attribute(group_id, server_ip, attribute, default_values[attribute])


def import_group_data(group_id: int, data_to_import: Dict[str, Any]) -> bool:
    """导入并覆盖一个群组的配置。"""
    # 基础验证
    if not isinstance(data_to_import, dict) or "servers" not in data_to_import:
        return False
    if not isinstance(data_to_import["servers"], list):
        return False

    data = _load_data()
    group_id_str = str(group_id)
    # 在赋值前确保完整结构存在
    _ensure_group_data_exists(data, group_id_str)
    data[group_id_str]['servers'] = data_to_import.get("servers", [])
    data[group_id_str]['footer'] = data_to_import.get("footer", "")
    data[group_id_str]['show_offline_by_default'] = data_to_import.get("show_offline_by_default", False)
    _save_data(data)
    return True


def export_group_data(group_id: int) -> Dict[str, Any]:
    """导出一个群组的完整配置数据。"""
    data = _load_data()
    group_id_str = str(group_id)
    # 如果群组不存在，确保返回默认结构
    _ensure_group_data_exists(data, group_id_str)
    return data[group_id_str]

# --- 页脚管理 ---

def get_footer(group_id: int) -> str:
    """获取一个群组的页脚。"""
    data = _load_data()
    group_id_str = str(group_id)
    return data.get(group_id_str, {}).get("footer", "")


def add_footer(group_id: int, footer_text: str):
    """为一个群组添加或更新页脚。"""
    data = _load_data()
    group_id_str = str(group_id)
    _ensure_group_data_exists(data, group_id_str)
    data[group_id_str]["footer"] = footer_text
    _save_data(data)


def clear_footer(group_id: int):
    """清除一个群组的页脚。"""
    add_footer(group_id, "")
