import json
import os
from typing import List, Dict

# 数据存储路径：data/mc_update/subscription.json
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "subscription.json")

class DataManager:
    def __init__(self):
        self._ensure_file()
        self.data = self._load()

    def _ensure_file(self):
        if not os.path.exists(DATA_DIR):
            os.mkdir(DATA_DIR)
        if not os.path.exists(DATA_FILE):
            # 初始化空配置
            initial_data = {
                "groups": [],
                "last_version": {
                    "release": "",
                    "snapshot": ""
                }
            }
            self._save(initial_data)

    def _load(self) -> Dict:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"groups": [], "last_version": {"release": "", "snapshot": ""}}

    def _save(self, data: Dict):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # --- 对外接口 ---

    def get_subscribed_groups(self) -> List[int]:
        return self.data.get("groups", [])

    def add_group(self, group_id: int) -> bool:
        """添加订阅，返回 True 表示添加成功，False 表示已存在"""
        if group_id not in self.data["groups"]:
            self.data["groups"].append(group_id)
            self._save(self.data)
            return True
        return False

    def remove_group(self, group_id: int) -> bool:
        """移除订阅，返回 True 表示移除成功"""
        if group_id in self.data["groups"]:
            self.data["groups"].remove(group_id)
            self._save(self.data)
            return True
        return False

    def get_last_version(self, type_key: str) -> str:
        """获取本地记录的版本号 (type_key: 'release' or 'snapshot')"""
        return self.data.get("last_version", {}).get(type_key, "")

    def update_version(self, type_key: str, version: str):
        """更新本地记录的版本号"""
        if "last_version" not in self.data:
            self.data["last_version"] = {}
        self.data["last_version"][type_key] = version
        self._save(self.data)

# 单例模式导出
data_manager = DataManager()