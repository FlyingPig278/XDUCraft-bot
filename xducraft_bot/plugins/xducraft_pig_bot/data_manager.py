import json
import os
from typing import Any, Dict, Optional

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_DATA_FILE = os.path.join(DEFAULT_DATA_DIR, "pig_config.json")
DEFAULT_MAX_FORWARD_RESULTS = 5


class DataManager:
    def __init__(self, data_dir: Optional[str] = None, data_file: Optional[str] = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.data_file = data_file or DEFAULT_DATA_FILE
        self._ensure_file()
        self.data = self._load()

    @staticmethod
    def _default_group_config() -> Dict[str, bool]:
        return {
            "auto_push_enabled": False,
            "query_enabled": True,
        }

    def _default_data(self) -> Dict[str, Any]:
        return {
            "max_forward_results": DEFAULT_MAX_FORWARD_RESULTS,
            "groups": {},
        }

    @staticmethod
    def _normalize_max_forward_results(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return DEFAULT_MAX_FORWARD_RESULTS
        return max(1, parsed)

    def _normalize_data(self, raw_data: Any) -> Dict[str, Any]:
        data = self._default_data()
        if not isinstance(raw_data, dict):
            return data

        raw_groups = raw_data.get("groups", {})
        if not isinstance(raw_groups, dict):
            return data

        data["max_forward_results"] = self._normalize_max_forward_results(
            raw_data.get("max_forward_results", DEFAULT_MAX_FORWARD_RESULTS)
        )

        normalized_groups: Dict[str, Dict[str, bool]] = {}
        for group_id, cfg in raw_groups.items():
            group_key = str(group_id)
            group_cfg = self._default_group_config()

            if isinstance(cfg, dict):
                group_cfg["auto_push_enabled"] = bool(cfg.get("auto_push_enabled", False))
                group_cfg["query_enabled"] = bool(cfg.get("query_enabled", True))

            normalized_groups[group_key] = group_cfg

        data["groups"] = normalized_groups
        return data

    def _ensure_file(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        if not os.path.exists(self.data_file):
            self._save(self._default_data())

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            normalized_data = self._normalize_data(raw_data)
            if normalized_data != raw_data:
                self._save(normalized_data)
            return normalized_data
        except Exception:
            return self._default_data()

    def reload(self) -> None:
        self._ensure_file()
        self.data = self._load()

    def _save(self, data: Dict[str, Any]) -> None:
        normalized_data = self._normalize_data(data)
        os.makedirs(self.data_dir, exist_ok=True)

        temp_file = f"{self.data_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(normalized_data, f, indent=4, ensure_ascii=False)

        os.replace(temp_file, self.data_file)
        self.data = normalized_data

    def _ensure_group(self, group_id: int) -> Dict[str, bool]:
        self.reload()
        group_key = str(group_id)
        groups = self.data.setdefault("groups", {})
        if group_key not in groups:
            groups[group_key] = self._default_group_config()
            self._save(self.data)
            return self.data["groups"][group_key]
        return groups[group_key]

    def get_group_config(self, group_id: int) -> Dict[str, bool]:
        cfg = self._ensure_group(group_id)
        return {
            "auto_push_enabled": bool(cfg.get("auto_push_enabled", False)),
            "query_enabled": bool(cfg.get("query_enabled", True)),
        }

    def set_auto_push_enabled(self, group_id: int, enabled: bool) -> bool:
        cfg = self._ensure_group(group_id)
        if cfg["auto_push_enabled"] == enabled:
            return False
        cfg["auto_push_enabled"] = enabled
        self._save(self.data)
        return True

    def set_query_enabled(self, group_id: int, enabled: bool) -> bool:
        cfg = self._ensure_group(group_id)
        if cfg["query_enabled"] == enabled:
            return False
        cfg["query_enabled"] = enabled
        self._save(self.data)
        return True

    def list_auto_push_groups(self) -> list[int]:
        self.reload()
        groups: list[int] = []
        for group_key, cfg in self.data.get("groups", {}).items():
            if not isinstance(cfg, dict):
                continue
            if not bool(cfg.get("auto_push_enabled", False)):
                continue
            try:
                groups.append(int(group_key))
            except ValueError:
                continue
        return groups

    def get_max_forward_results(self) -> int:
        self.reload()
        return self._normalize_max_forward_results(
            self.data.get("max_forward_results", DEFAULT_MAX_FORWARD_RESULTS)
        )


# singleton export
pig_data_manager = DataManager()

