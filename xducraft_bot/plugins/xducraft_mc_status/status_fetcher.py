import asyncio
from typing import List, Dict, Any, Tuple, Optional

import httpx

from . import data_manager
from .constants import DEFAULT_SERVER_PRIORITY


async def get_single_server_status(ip: str) -> Dict[str, Any]:
    """获取单个Minecraft服务器的状态。"""
    url = f"https://mc.sjtu.cn/custom/serverlist/?query={ip}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            data['original_query'] = ip
            if not data.get('online'):
                data.setdefault('hostname', ip)
                data.setdefault('port', 0)
            return data
        except httpx.RequestError as e:
            return {"online": False, "hostname": ip, "port": 0, "original_query": ip, "error": str(e)}


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
