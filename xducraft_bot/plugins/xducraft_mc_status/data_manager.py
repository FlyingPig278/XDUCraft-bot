import json
import os
from typing import Dict, List, Any

from xducraft_bot.plugins.xducraft_mc_status.constants import DEFAULT_SERVER_PRIORITY

# 定义存储数据的文件路径，放在插件目录下的 data 文件夹里
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "server_data.json")


def _load_data() -> dict:
    """
    内部函数：从文件中加载所有数据。
    如果文件不存在或为空，返回一个空字典。
    """
    if not os.path.exists(DATA_FILE):
        return {}

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # 如果文件内容不是有效的JSON，返回空字典
            return {}


def _save_data(data: Dict[str, Any]):
    """
    内部函数：将所有数据保存到文件中。
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _ensure_group_data_exists(data: Dict[str, Any], group_id_str: str):
    """确保指定群ID的数据结构存在并初始化"""
    if group_id_str not in data:
        data[group_id_str] = {
            "servers": [],
            "footer": ""
        }


def _find_server_index(servers_list: List[Dict[str, Any]], server_ip: str) -> int:
    """
    内部函数：查找指定服务器 IP 在列表中的索引位置。
    未找到返回 -1。
    """
    for i, server_info in enumerate(servers_list):
        if server_info.get('ip') == server_ip:
            return i
    return -1


def set_server_attribute(group_id: int, server_ip: str, attribute: str, value: Any) -> bool:
    """
    为指定服务器设置/修改单个属性值。

    Args:
        group_id (int): 群聊ID。
        server_ip (str): 服务器IP。
        attribute (str): 要修改的属性名称（如 'tag', 'priority'）。
        value (Any): 要设置的新值。

    Returns:
        bool: 如果服务器存在且属性成功修改则为 True，否则为 False。
    """
    data = _load_data()
    group_id_str = str(group_id)

    # 1. 确保数据结构存在
    _ensure_group_data_exists(data, group_id_str)
    if group_id_str not in data or "servers" not in data[group_id_str]:
        return False  # 群数据结构不存在

    servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]
    index = _find_server_index(servers_list, server_ip)

    if index != -1:
        # 2. 检查并阻止修改 'ip' 本身
        if attribute == 'ip':
            print("警告：不能通过此函数修改服务器IP本身。")
            return False

        # 3. 执行修改
        servers_list[index][attribute] = value

        # 4. 保存数据
        _save_data(data)
        return True

    return False


def migrate_server_ip(group_id: int, old_ip: str, new_ip: str) -> bool:
    """
    将旧 IP 的所有配置信息迁移到新 IP，并删除旧记录。

    Args:
        group_id (int): 群聊ID。
        old_ip (str): 服务器旧的IP。
        new_ip (str): 服务器新的IP。

    Returns:
        bool: 迁移成功返回 True，否则返回 False。
    """
    data = _load_data()
    group_id_str = str(group_id)

    if group_id_str not in data or "servers" not in data[group_id_str]:
        return False

    servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]

    # 1. 检查新 IP 是否已存在，防止冲突
    if any(server_info.get('ip') == new_ip for server_info in servers_list):
        print(f"迁移失败：新 IP '{new_ip}' 已存在于列表中。")
        return False

    # 2. 查找旧 IP 记录的索引
    old_index = _find_server_index(servers_list, old_ip)

    if old_index != -1:
        # 3. 执行迁移：更新 IP 字段
        servers_list[old_index]['ip'] = new_ip

        # 4. 保存数据
        _save_data(data)
        return True

    # 旧 IP 不存在
    return False


def get_server_list(group_id: int) -> List[Dict[str, Any]]:
    """
    获取指定群绑定的所有服务器信息列表。
    返回结构：List[{'ip': str, 'tag': str, 'tag_color': str, 'server_type': str, 'parent_ip': str, 'priority': int}]
    """
    data = _load_data()
    group_id_str =str(group_id)
    # 返回服务器信息列表，不存在时返回空列表
    return data.get(group_id_str,{}).get("servers",[])


def add_server(group_id: int, server_ip: str, tag: str = "", tag_color: str = "", server_type: str = "standalone",
               parent_ip: str = "", priority: int = DEFAULT_SERVER_PRIORITY) -> bool:  # <--- 新增 priority 参数
    """
    为指定群添加一个服务器IP及其相关属性。

    Args:
        group_id (int): 接收指令的群聊ID。
        server_ip: 服务器IP或域名。
        tag: 标签文本。
        tag_color: 标签颜色（Hex或名称）。
        server_type: 服务器角色（'parent', 'child', 'standalone'），默认为 'standalone'。
        parent_ip: 所属主服的IP，仅对 'child' 有效。
        priority: 自定义排序优先级，数字越小越靠前，默认为 DEFAULT_SERVER_PRIORITY。
    """
    data = _load_data()
    group_id_str = str(group_id)

    # 1. 初始化数据结构
    _ensure_group_data_exists(data, group_id_str)

    servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]

    # 2. 检查 IP 是否已存在 (新逻辑: 遍历字典列表)
    ip_exists = any(server_info.get('ip') == server_ip for server_info in servers_list)

    if not ip_exists:
        # 3. 创建并添加包含所有属性的新的服务器信息字典
        new_server_info = {
            "ip": server_ip,
            "tag": tag,
            "tag_color": tag_color,
            "server_type": server_type.lower(),
            "parent_ip": parent_ip,
            "priority": priority
        }
        servers_list.append(new_server_info)
        _save_data(data)
        return True

    return False


def remove_server(group_id: int, server_ip: str) -> bool:
    """
    从指定群中移除一个服务器IP及其所有信息。
    """
    data = _load_data()
    group_id_str = str(group_id)

    if group_id_str in data:
        servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]
        initial_count = len(servers_list)

        # 核心逻辑：使用列表推导式，保留 'ip' 不等于要移除的 server_ip 的字典
        data[group_id_str]["servers"] = [
            s for s in servers_list if s['ip'] != server_ip
        ]

        # 检查是否实际移除了元素
        if len(data[group_id_str]["servers"]) < initial_count:
            _save_data(data)
            return True

    # 服务器不存在或群不存在
    return False


def get_footer(group_id: int) -> str:
    """
    获取指定群设定的footer
    """
    data = _load_data()
    group_id_str = str(group_id)
    # 返回footer，不存在时返回空字符串
    return data.get(group_id_str, {}).get("footer", "")


def add_footer(group_id: int, footer_text: str) -> bool:
    """
    为指定群添加一个footer
    """
    data = _load_data()
    group_id_str = str(group_id)  # JSON中的键必须为str

    # 统一初始化数据结构，确保 "servers" 键存在
    _ensure_group_data_exists(data, group_id_str)

    data[group_id_str]["footer"] = footer_text
    _save_data(data)
    return True


def clear_footer(group_id: int) -> bool:
    """
    从指定群中移除footer
    """
    data = _load_data()
    group_id_str = str(group_id)

    if group_id_str in data:
        data[group_id_str]["footer"] = ""
        _save_data(data)
        return True
    return False


def clear_server_attribute(group_id: int, server_ip: str, attribute: str) -> bool:
    """
    将指定服务器的属性值设置为空字符串（""），达到逻辑上的“移除”效果。

    Args:
        group_id (int): 群聊ID。
        server_ip (str): 服务器IP。
        attribute (str): 要清空的属性名称。

    Returns:
        bool: 如果服务器存在且属性成功清空则为 True，否则为 False。
    """
    data = _load_data()
    group_id_str = str(group_id)

    # 1. 检查群数据结构是否存在
    if group_id_str not in data or "servers" not in data[group_id_str]:
        return False

    servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]
    index = _find_server_index(servers_list, server_ip)

    if index != -1:
        # 2. 检查并防止清空关键属性
        if attribute in ['ip', 'server_type']:
            print(f"警告：不支持清空关键属性 '{attribute}'。")
            return False

        if attribute == 'priority':
            servers_list[index]['priority'] = DEFAULT_SERVER_PRIORITY
            _save_data(data)
            return True

        # 3. 执行清空：将值设置为 ""
        servers_list[index][attribute] = ""

        # 4. 保存数据
        _save_data(data)
        return True

    return False


def get_server_attribute(group_id: int, server_ip: str, attribute: str, default_value: Any = None) -> Any:
    """
    获取指定服务器的单个属性值。
    """
    data = _load_data()
    group_id_str = str(group_id)

    if group_id_str in data:
        servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]
        index = _find_server_index(servers_list, server_ip)

        if index != -1:
            return servers_list[index].get(attribute, default_value)

    return default_value


def get_server_tag(group_id: int, server_ip: str) -> str:
    """获取指定服务器的标签（tag）。"""
    return get_server_attribute(group_id, server_ip, 'tag', default_value="")


def get_server_tag_color(group_id: int, server_ip: str) -> str:
    """获取指定服务器的标签颜色（tag_color）。"""
    return get_server_attribute(group_id, server_ip, 'tag_color', default_value="")


def get_server_type(group_id: int, server_ip: str) -> str:
    """获取指定服务器的类型（server_type）。"""
    return get_server_attribute(group_id, server_ip, 'server_type', default_value="standalone")


def get_server_parent_ip(group_id: int, server_ip: str) -> str:
    """获取指定服务器所属主服的IP（parent_ip）。"""
    return get_server_attribute(group_id, server_ip, 'parent_ip', default_value="")


def get_server_priority(group_id: int, server_ip: str) -> int:
    """获取指定服务器的优先级（priority）。"""
    # 注意：如果 priority 不存在，返回 add_server 中设置的默认值 100
    return get_server_attribute(group_id, server_ip, 'priority', default_value=DEFAULT_SERVER_PRIORITY)


def get_server_info(group_id: int, server_ip: str) -> Dict[str, Any]:
    """
    获取指定群中某个服务器IP的完整信息字典。
    """
    data = _load_data()
    group_id_str = str(group_id)

    if group_id_str in data:
        servers_list: List[Dict[str, Any]] = data[group_id_str]["servers"]
        # 使用列表推导式或 next() 查找匹配项
        for server_info in servers_list:
            if server_info.get('ip') == server_ip:
                return server_info

    return {}  # 未找到则返回空字典


