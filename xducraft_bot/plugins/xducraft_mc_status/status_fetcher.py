import asyncio
from typing import List, Dict, Any, Tuple

import httpx

from .data_manager import get_server_list


#获取单个Minecraft服务器的状态。
async def get_single_server_status(ip: str) -> Dict[str, Any]:
    url = f"https://mc.sjtu.cn/custom/serverlist/?query={ip}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()  # 如果状态码不是200，抛出HTTPStatusError
            data = response.json()
            data['original_query'] = ip   # 使用原始ip而非解析ip，避免多线服务器被解析为单条线路awa

            # API返回的离线数据可能缺少 hostname/port，这里需要判断并设置默认值
            if not data.get('online'):
                # 显式添加 hostname 和 port 避免 KeyError，以便后续处理（但它们可能没有实际意义）
                if 'hostname' not in data:
                    data['hostname'] = None # 或 ip, 取决于你更倾向于记录什么
                if 'port' not in data:
                    data['port'] = 0
            return data
        except httpx.RequestError as e:
            print(f"请求服务器 {ip} 失败: {e}")
            return {"online": False,
                    "hostname": None,
                    "port": 0,
                    "original_query": ip,
                    "error": str(e)}


# # 获取一个群所有服务器的状态。
# async def get_all_servers_status(group_id: int) -> List[Dict[str, Any]]:
#     server_list = get_server_list(group_id)
#
#     if not server_list:
#         return []
#
#     # 1. 并发获取所有服务器状态
#     tasks = [get_single_server_status(server.get('ip')) for server in server_list]
#     results = await asyncio.gather(*tasks, return_exceptions=True)
#
#     # 2. 合并逻辑：使用字典存储已处理的服务器
#     merged_servers: Dict[Tuple[str, int], Dict[str, Any]] = {}
#
#     # 处理并发任务的结果
#     for res in results:
#         # 跳过异常
#         if isinstance(res, Exception):
#             print(f"并发任务执行失败: {res}")
#             continue
#
#         original_query = res.get('original_query', 'UNKNOWN_QUERY')
#
#         if res.get('online'):
#             # --- 在线服务器合并逻辑 (使用 hostname + port) ---
#             hostname = res.get('hostname')
#             port_value = res.get('port', 25565)  # 默认端口
#
#             try:
#                 # 即使是 '63176' (str) 也会成功转换为 63176 (int)
#                 port = int(port_value)
#             except (ValueError, TypeError):
#                 # 如果转换失败（例如返回了无效字符串），则回退到默认值
#                 # port = 25565
#                 raise
#
#             # 如果 hostname 不存在（极少发生，但作为安全措施）
#             if not hostname:
#                 key = ('ONLINE_NO_HOST', original_query)
#             else:
#                 key = (hostname, port)
#
#             if key in merged_servers:
#                 # 找到匹配，合并 original_query
#                 existing_data = merged_servers[key]
#                 current_queries = existing_data['original_query'].split('|')
#                 if original_query not in current_queries:
#                     existing_data['original_query'] += f"|{original_query}"
#             else:
#                 # 新的在线服务器
#                 merged_servers[key] = res
#
#         else:
#             # --- 离线/错误服务器逻辑 (使用 original_query 作为唯一键，不合并) ---
#             # 即使两个离线查询指向同一地址，由于无法确定，也保持独立显示
#             key = ('OFFLINE', original_query)
#             # 保证 key 唯一
#             if key not in merged_servers:
#                 merged_servers[key] = res
#
#         # 3. 将合并后的字典值转换回列表返回
#     return list(merged_servers.values())


# 获取一个群所有服务器的状态。

# 获取一个群所有服务器的状态。
async def get_all_servers_status(group_id: int) -> List[Dict[str, Any]]:
    # server_list 包含所有元数据 (ip, tag, priority, type...)
    server_list = get_server_list(group_id)

    if not server_list:
        return []

    # 1. 并发查询
    tasks = [get_single_server_status(server.get('ip')) for server in server_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 2. 初始合并：将 data_manager_info 注入到状态结果中
    initial_data_list = []

    # 遍历原始服务器列表和查询结果（两者顺序和长度相同）
    for original_server_info, res in zip(server_list, results):

        # 统一状态数据结构
        if isinstance(res, Exception):
            status_data = {"online": False, "original_query": original_server_info['ip'], "error": str(res)}
        else:
            status_data = res

        # 将状态数据和元数据组合
        initial_data_list.append({
            **status_data,
            "data_manager_info": original_server_info
        })

    # 3. 最终合并逻辑：基于 IP:Port 查找重复项，并合并 original_query
    merged_servers: Dict[Tuple[str, int], Dict[str, Any]] = {}

    for server_data in initial_data_list:
        original_query = server_data.get('original_query', 'UNKNOWN_QUERY')

        if server_data.get('online'):
            # --- 在线服务器合并逻辑 (使用 hostname + port) ---
            hostname = server_data.get('hostname', '')
            port_value = server_data.get('port', 25565)

            try:
                port = int(port_value)
            except (ValueError, TypeError):
                # 端口解析失败，使用默认值
                # port = 25565
                raise

            # 确定合并键 (key)
            key = (hostname, port)

            if key in merged_servers:
                # 找到匹配项，执行合并：
                existing_data = merged_servers[key]

                # a. 合并 original_query 字符串
                current_queries = existing_data['original_query'].split('|')
                if original_query not in current_queries:
                    existing_data['original_query'] += f"|{original_query}"

                # b. 忽略当前重复项的 data_manager_info (因为要保留第一个)
                # 这一步通过不修改 existing_data['data_manager_info'] 隐式完成。

            else:
                # 新的在线服务器：直接添加
                merged_servers[key] = server_data

        else:
            # --- 离线/错误服务器逻辑 (不合并，独立显示) ---
            # 即使两个离线查询指向同一地址，也保持独立显示
            key = ('OFFLINE', original_query)
            if key not in merged_servers:
                merged_servers[key] = server_data

    # 4. 返回最终合并后的列表
    return list(merged_servers.values())

def preprocess_server_data(server_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """修正在线玩家数量和匿名玩家，并返回处理后的列表。"""
    for res in server_data_list:
        if res['online'] and res.get('players', {}).get('online') != 0 and res.get('players', {}).get('sample'):
            valid_players = []
            print(f"现在的res是：{res}")
            sample = res['players']['sample']
            for player in sample:
                if player.get('id') == '00000000-0000-0000-0000-000000000000' and player.get('name') == 'Anonymous Player':
                    # res['players']['online'] -= 1
                    pass
                else:
                    valid_players.append(player)
            res['players']['sample'] = valid_players
    return server_data_list

def prepare_data_for_display(
        server_data_list: List[Dict[str, Any]],
        show_all_servers: bool
) -> List[Dict[str, Any]]:
    """根据展示设置过滤和排序数据。（现在调用通用排序键）"""

    # 1. 过滤离线服务器
    if not show_all_servers:
        server_data_list = [res for res in server_data_list if res.get('online')]

    # 2. 排序：使用组合键
    server_data_list = sorted(server_data_list, key=lambda x: (
        # not x.get('online'),  # 1. 在线状态优先 //由于子服排序存在问题，暂时禁用该排序。

        # 2. 调用通用排序键，但必须从 'data_manager_info' 中提取元数据
        # *get_server_display_key(x.get('data_manager_info', {})) //由于注释掉了1.，此处不允许*语法

        get_server_display_key(x.get('data_manager_info', {}))
    ))

    return server_data_list

def get_active_server_count(display_data: list[dict[str, Any]]) -> int:
    active_server_count:int=0
    for server_data in display_data:
        if server_data.get('online') and server_data['players'].get('online') != 0 and server_data.get('players', {}).get('sample'):
            active_server_count += 1
    return active_server_count

def get_server_display_key(server_info: Dict[str, Any]) -> Tuple:
    """
    生成用于服务器排序的元组键。
    排序优先级：自定义 Priority > 服务器类型 (Parent/Standalone) > 主服 IP。
    """
    # 从字典中安全地获取数据，并设置合理的默认值
    priority = server_info.get('priority', 999)      # 默认低优先级
    server_type = server_info.get('server_type', 'standalone')
    parent_ip = server_info.get('parent_ip', '')

    return (
        # 1. 自定义 Priority (数字小靠前)
        priority,
        # 2. 服务器类型：Parent (False/0) 优先于其他 (True/1)
        server_type != 'parent',
        # 3. 主服 IP (用于将子服排在对应主服下面)
        parent_ip,
        # 4. IP 字母顺序 (作为稳定排序)
        server_info.get('ip', '')
    )