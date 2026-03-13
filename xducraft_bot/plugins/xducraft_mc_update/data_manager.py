import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_DATA_FILE = os.path.join(DEFAULT_DATA_DIR, "subscription.json")


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

class DataManager:
    VERSION_KEYS = ("release", "snapshot")

    def __init__(self, data_dir: Optional[str] = None, data_file: Optional[str] = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.data_file = data_file or DEFAULT_DATA_FILE
        self._ensure_file()
        self.data = self._load()

    def _default_data(self) -> Dict[str, Any]:
        return {
            "groups": [],
            "versions": {
                key: {
                    "id": "",
                    "release_time": ""
                }
                for key in self.VERSION_KEYS
            }
        }

    def _normalize_data(self, raw_data: Any) -> Dict[str, Any]:
        data = self._default_data()
        if not isinstance(raw_data, dict):
            return data

        groups = raw_data.get("groups", [])
        if isinstance(groups, list):
            normalized_groups = []
            seen_groups = set()
            for group_id in groups:
                try:
                    normalized_id = int(group_id)
                except (TypeError, ValueError):
                    continue

                if normalized_id in seen_groups:
                    continue

                seen_groups.add(normalized_id)
                normalized_groups.append(normalized_id)

            data["groups"] = normalized_groups

        versions = raw_data.get("versions", {})
        legacy_versions = raw_data.get("last_version", {})

        for key in self.VERSION_KEYS:
            version_data = versions.get(key, {}) if isinstance(versions, dict) else {}

            version_id = ""
            release_time = ""

            if isinstance(version_data, dict):
                version_id = str(version_data.get("id", "") or "")
                release_time = str(version_data.get("release_time", "") or "")
            elif isinstance(version_data, str):
                version_id = version_data

            if not version_id and isinstance(legacy_versions, dict):
                version_id = str(legacy_versions.get(key, "") or "")

            data["versions"][key] = {
                "id": version_id,
                "release_time": release_time,
            }

        data["last_version"] = {
            key: data["versions"][key]["id"]
            for key in self.VERSION_KEYS
        }
        return data

    def _ensure_file(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if not os.path.exists(self.data_file):
            self._save(self._default_data())

    def _load(self) -> Dict:
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return self._normalize_data(json.load(f))
        except Exception:
            return self._default_data()

    def reload(self):
        self._ensure_file()
        self.data = self._load()

    def _save(self, data: Dict):
        normalized_data = self._normalize_data(data)
        os.makedirs(self.data_dir, exist_ok=True)

        temp_file = f"{self.data_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(normalized_data, f, indent=4, ensure_ascii=False)

        os.replace(temp_file, self.data_file)
        self.data = normalized_data

    def _should_accept_version(self, current: Dict[str, str], candidate: Dict[str, str]) -> bool:
        current_id = str(current.get("id", "") or "")
        candidate_id = str(candidate.get("id", "") or "")
        if not candidate_id:
            return False
        if not current_id:
            return True
        if current_id == candidate_id:
            return False

        current_time = _parse_iso_datetime(str(current.get("release_time", "") or ""))
        candidate_time = _parse_iso_datetime(str(candidate.get("release_time", "") or ""))

        if current_time and candidate_time:
            return candidate_time > current_time
        if current_time and not candidate_time:
            return False
        if not current_time and candidate_time:
            return True

        return True

    # --- 对外接口 ---

    def get_subscribed_groups(self) -> List[int]:
        self.reload()
        return self.data.get("groups", [])

    def add_group(self, group_id: int) -> bool:
        """添加订阅，返回 True 表示添加成功，False 表示已存在"""
        self.reload()
        if group_id not in self.data["groups"]:
            self.data["groups"].append(group_id)
            self._save(self.data)
            return True
        return False

    def remove_group(self, group_id: int) -> bool:
        """移除订阅，返回 True 表示移除成功"""
        self.reload()
        if group_id in self.data["groups"]:
            self.data["groups"].remove(group_id)
            self._save(self.data)
            return True
        return False

    def get_last_record(self, type_key: str) -> Dict[str, str]:
        self.reload()
        if type_key not in self.VERSION_KEYS:
            return {"id": "", "release_time": ""}

        record = self.data.get("versions", {}).get(type_key, {})
        return {
            "id": str(record.get("id", "") or ""),
            "release_time": str(record.get("release_time", "") or ""),
        }

    def get_last_version(self, type_key: str) -> str:
        """获取本地记录的版本号 (type_key: 'release' or 'snapshot')"""
        return self.get_last_record(type_key)["id"]

    def update_version(self, type_key: str, version: str, release_time: str = "") -> bool:
        """更新本地记录的版本号"""
        if type_key not in self.VERSION_KEYS:
            return False

        self.reload()
        current_record = self.data.get("versions", {}).get(type_key, {"id": "", "release_time": ""})
        candidate_record = {
            "id": str(version or ""),
            "release_time": str(release_time or ""),
        }

        if not self._should_accept_version(current_record, candidate_record):
            return False

        self.data.setdefault("versions", {})[type_key] = candidate_record
        self.data["last_version"] = {
            key: self.data["versions"].get(key, {}).get("id", "")
            for key in self.VERSION_KEYS
        }
        self._save(self.data)
        return True

# 单例模式导出
data_manager = DataManager()