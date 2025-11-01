import json
import zlib
import base64
from typing import List, Dict, Any

# --- Constants for compact array indices from App.vue ---
S_IP = 0
S_COMMENT = 1
S_TAG = 2
S_TAG_COLOR = 3
S_IGNORE = 4
S_CHILDREN = 5


def _build_tree(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts a flat list of servers into a nested tree structure."""
    server_map = {s['ip']: {**s, 'children': []} for s in servers}
    tree = []
    for server in server_map.values():
        if server.get('parent_ip'):
            parent = server_map.get(server['parent_ip'])
            if parent:
                parent['children'].append(server)
            else:
                tree.append(server)  # Orphan node, treat as a root
        else:
            tree.append(server)
    return tree


def _flatten_tree(servers_tree: List[Dict[str, Any]], parent_ip: str = "") -> List[Dict[str, Any]]:
    """Converts a nested tree of servers back into a flat list."""
    flat_list = []
    for server in servers_tree:
        server['parent_ip'] = parent_ip
        children = server.pop('children', [])
        # Bot data model doesn't need these UI-specific fields
        server.pop('tag_color_with_hash', None)
        server.pop('selectedPreset', None)
        flat_list.append(server)
        if children:
            flat_list.extend(_flatten_tree(children, server['ip']))
    return flat_list


def _json_to_compact_array(servers: List[Dict[str, Any]]) -> List[Any]:
    """Recursively converts a server tree to a compact array."""
    if not servers:
        return []
    return [
        [
            s.get('ip'),
            s.get('comment') or 0,
            s.get('tag') or 0,
            s.get('tag_color') or 0,
            1 if s.get('ignore_in_list') else 0,
            _json_to_compact_array(s.get('children', [])) or 0
        ]
        for s in servers
    ]


def _compact_array_to_json(compact_data: List[Any]) -> List[Dict[str, Any]]:
    """Recursively converts a compact array back to a server tree."""
    if not compact_data:
        return []
    servers = []
    for item in compact_data:
        children_data = item[S_CHILDREN]
        children = _compact_array_to_json(children_data) if isinstance(children_data, list) else []

        server = {
            'ip': item[S_IP],
            'comment': item[S_COMMENT] or "",
            'tag': item[S_TAG] or "",
            'tag_color': item[S_TAG_COLOR] or "",
            'ignore_in_list': item[S_IGNORE] == 1,
            'children': children
        }
        servers.append(server)
    return servers


def _to_url_safe_base64(b64_bytes: bytes) -> str:
    """Converts standard Base64 to URL-safe Base64."""
    return b64_bytes.replace(b'+', b'-').replace(b'/', b'_').rstrip(b'=').decode('ascii')


def _from_url_safe_base64(url_safe_b64_str: str) -> bytes:
    """Converts URL-safe Base64 back to standard Base64."""
    b64_str = url_safe_b64_str.replace('-', '+').replace('_', '/')
    padding = -len(b64_str) % 4
    if padding:
        b64_str += '=' * padding
    return b64_str.encode('ascii')


def compress_config(group_data: Dict[str, Any]) -> str:
    """
    Compresses a group's configuration dictionary into a URL-safe string.
    """
    try:
        show_offline_by_default = 0  # This setting is not used in the bot, hardcode to 0 for compatibility
        server_tree = _build_tree(group_data.get('servers', []))
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
        print(f"Compression failed: {e}")
        return ""


def decompress_config(encoded_string: str) -> Dict[str, Any] | None:
    """
    Decompresses a URL-safe string back into a group's configuration dictionary.
    """
    try:
        base64_bytes = _from_url_safe_base64(encoded_string)
        binary_string = base64.b64decode(base64_bytes)
        inflated = zlib.decompress(binary_string).decode('utf-8')
        compact_structure = json.loads(inflated)
        server_tree = _compact_array_to_json(compact_structure[2])
        flat_servers = _flatten_tree(server_tree)
        return {
            'footer': compact_structure[0] or "",
            'servers': flat_servers
        }
    except Exception as e:
        print(f"Decompression failed: {e}")
        return None
