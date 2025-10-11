# 定义存储数据的文件路径，放在插件目录下的 data 文件夹里
# 注意：__file__ 必须在 NoneBot 插件的主文件中才能正确获取路径
import json
import os
from typing import Dict, Union

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "at_me_switch.json")  # 专门用于存储开关状态的文件


def _load_data() -> Dict[str, bool]:
    """
    内部函数：从文件中加载所有群聊开关数据。
    返回格式：{'123456': True, '654321': False}
    """
    if not os.path.exists(DATA_FILE):
        return {}

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print(f"警告：{DATA_FILE} 内容不是有效的JSON，将使用空数据。")
            return {}


def _save_data(data: Dict[str, bool]):
    """
    内部函数：将所有群聊开关数据保存到文件中。
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_at_me_status(group_id: Union[int, str]) -> bool:
    """
    获取指定群聊的 @喵 功能开关状态。
    """
    group_id_str = str(group_id)
    data = _load_data()
    # 默认是 False (关闭)
    return data.get(group_id_str, False)


def set_at_me_status(group_id: Union[int, str], status: bool) -> None:
    """
    设置指定群聊的 @喵 功能开关状态。
    """
    group_id_str = str(group_id)
    data = _load_data()
    data[group_id_str] = status
    _save_data(data)

