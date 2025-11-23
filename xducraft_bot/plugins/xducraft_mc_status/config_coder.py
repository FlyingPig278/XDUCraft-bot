import json
import zlib
import base64
from typing import List, Dict, Any

# --- 紧凑数组索引常量 (与 App.vue 保持一致) ---
S_IP = 0
S_COMMENT = 1
S_TAG = 2
S_TAG_COLOR = 3
S_IGNORE = 4
S_HIDE_IP = 5      # 新增
S_DISPLAY_NAME = 6 # 新增
S_CHILDREN = 7     # 原来的 S_CHILDREN 索引后移


def _build_tree(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将扁平的服务器列表转换为嵌套的树形结构。"""
    server_map = {s['ip']: {**s, 'children': []} for s in servers}
    tree = []
    for server in server_map.values():
        if server.get('parent_ip'):
            parent = server_map.get(server['parent_ip'])
            if parent:
                parent['children'].append(server)
            else:
                tree.append(server)  # 孤儿节点，视为根节点
        else:
            tree.append(server)
    return tree


def _flatten_tree(servers_tree: List[Dict[str, Any]], parent_ip: str = "") -> List[Dict[str, Any]]:
    """将嵌套的服务器树转换回扁平列表。"""
    flat_list = []
    for server in servers_tree:
        server['parent_ip'] = parent_ip
        children = server.pop('children', [])
        # 机器人数据模型不需要这些UI特定的字段
        server.pop('tag_color_with_hash', None)
        server.pop('selectedPreset', None)
        flat_list.append(server)
        if children:
            flat_list.extend(_flatten_tree(children, server['ip']))
    return flat_list


def _json_to_compact_array(servers: List[Dict[str, Any]]) -> List[Any]:
    """递归地将服务器树转换为紧凑数组格式。"""
    if not servers:
        return []
    return [
        [
            s.get('ip'),
            s.get('comment') or 0,
            s.get('tag') or 0,
            s.get('tag_color') or 0,
            1 if s.get('ignore_in_list') else 0,
            1 if s.get('hide_ip') else 0,         # 新增
            s.get('display_name') or 0,           # 新增
            _json_to_compact_array(s.get('children', [])) or 0
        ]
        for s in servers
    ]


def _compact_array_to_json(compact_data: List[Any]) -> List[Dict[str, Any]]:
    """递归地将紧凑数组格式转换回服务器树。"""
    if not compact_data:
        return []
    servers = []
    for item in compact_data:
        children_data = item[S_CHILDREN] if len(item) > S_CHILDREN else [] # 兼容旧格式，没有hide_ip/display_name时
        children = _compact_array_to_json(children_data) if isinstance(children_data, list) else []

        server = {
            'ip': item[S_IP],
            'comment': item[S_COMMENT] or "",
            'tag': item[S_TAG] or "",
            'tag_color': item[S_TAG_COLOR] or "",
            'ignore_in_list': item[S_IGNORE] == 1,
            'hide_ip': item[S_HIDE_IP] == 1 if len(item) > S_HIDE_IP else False,          # 新增
            'display_name': item[S_DISPLAY_NAME] or "" if len(item) > S_DISPLAY_NAME else "", # 新增
            'children': children
        }
        servers.append(server)
    return servers


def _to_url_safe_base64(b64_bytes: bytes) -> str:
    """将标准的Base64转换为URL安全的Base64。"""
    return b64_bytes.replace(b'+', b'-').replace(b'/', b'_').rstrip(b'=').decode('ascii')


def _from_url_safe_base64(url_safe_b64_str: str) -> bytes:
    """将URL安全的Base64转换回标准的Base64。"""
    b64_str = url_safe_b64_str.replace('-', '+').replace('_', '/')
    padding = -len(b64_str) % 4
    if padding:
        b64_str += '=' * padding
    return b64_str.encode('ascii')


def compress_config(group_data: Dict[str, Any]) -> str:
    """
    将一个群组的配置字典压缩成URL安全的字符串。
    """
    try:
        # 此设置在机器人端未使用，硬编码为0以兼容旧版
        show_offline_by_default = 0
        server_tree = group_data.get('servers', []) # 数据已经是树形结构，直接使用
        compact_servers = _json_to_compact_array(server_tree)
        compact_structure = [
            group_data.get('footer') or 0,
            show_offline_by_default,
            compact_servers
        ]
        json_string = json.dumps(compact_structure, separators=(',', ':'))
        compressed = zlib.compress(json_string.encode('utf-8'), level=9)
        base64_encoded = base64.b64encode(compressed)
        return _to_url_safe_base64(base64_encoded)
    except Exception as e:
        print(f"压缩失败: {e}")
        return ""


def decompress_config(encoded_string: str) -> Dict[str, Any] | None:
    """
    将一个URL安全的字符串解压回群组的配置字典。
    """
    try:
        base64_bytes = _from_url_safe_base64(encoded_string)
        binary_string = base64.b64decode(base64_bytes)
        inflated = zlib.decompress(binary_string).decode('utf-8')
        compact_structure = json.loads(inflated)
        server_tree = _compact_array_to_json(compact_structure[2])
        return {
            'footer': compact_structure[0] or "",
            'show_offline_by_default': compact_structure[1] == 1,
            'servers': server_tree
        }
    except Exception as e:
        print(f"解压失败: {e}")
        return None