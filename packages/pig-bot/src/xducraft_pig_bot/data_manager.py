"""猪猪图配置：统一 SQLite 文档，旧 JSON 仅作一次性导入源。"""
import os
from typing import Any, Dict, Optional

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.config_store import ConfigDocumentStore
from xducraft_bot.shared.data_paths import plugin_data_dir

LEGACY_DATA_PATH = os.path.join(
    "xducraft_bot", "plugins", "xducraft_pig_bot", "data",
)
DEFAULT_DATA_DIR = str(plugin_data_dir(
    "pig_bot",
    os.path.join(os.path.dirname(__file__), "data"),
    legacy_relative_path=LEGACY_DATA_PATH,
))
DEFAULT_DATA_FILE = os.path.join(DEFAULT_DATA_DIR, "pig_config.json")
DEFAULT_MAX_FORWARD_RESULTS = 5


class DataManager:
    def __init__(self, *, legacy_config_path: str = DEFAULT_DATA_FILE,
                 configuration_db_path: Optional[str] = None):
        self._store = ConfigDocumentStore(
            "pig_bot", self._default_data, self._normalize_data,
            legacy_path=legacy_config_path, database_path=configuration_db_path,
        )
        self._store.load()

    def migrate_legacy_config(self) -> Dict[str, Any]:
        """Eagerly establish the one-way legacy JSON import."""
        return self._store.load()

    @staticmethod
    def _default_group_config() -> Dict[str, Any]:
        return {
            "auto_push_enabled": False,
            "query_enabled": False,
            "max_forward_results": DEFAULT_MAX_FORWARD_RESULTS,
        }

    @staticmethod
    def _default_data() -> Dict[str, Any]:
        return {"schema_version": 2, "groups": {}}

    @staticmethod
    def _normalize_max_forward_results(value: Any) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return DEFAULT_MAX_FORWARD_RESULTS

    def _normalize_data(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("pig_config_must_be_object")
        data = self._default_data()
        groups = raw.get("groups", {})
        if not isinstance(groups, dict):
            raise ValueError("pig_groups_must_be_object")
        legacy = raw.get("schema_version") != 2
        legacy_limit = self._normalize_max_forward_results(raw.get("max_forward_results", 5))
        known_groups = set()
        if legacy:
            known_groups.update(feature_gate.list_configured_groups())
        for group_id, values in groups.items():
            try:
                gid = int(group_id)
            except (TypeError, ValueError):
                continue
            if gid <= 0:
                continue
            known_groups.add(gid)
            cfg = self._default_group_config()
            if legacy:
                cfg["query_enabled"] = True
                cfg["max_forward_results"] = legacy_limit
            if isinstance(values, dict):
                cfg["auto_push_enabled"] = bool(values.get("auto_push_enabled", False))
                cfg["query_enabled"] = bool(values.get("query_enabled", cfg["query_enabled"]))
                cfg["max_forward_results"] = self._normalize_max_forward_results(
                    values.get("max_forward_results", cfg["max_forward_results"])
                )
            data["groups"][str(gid)] = cfg
        if legacy:
            for gid in known_groups:
                data["groups"].setdefault(str(gid), {
                    "auto_push_enabled": False,
                    "query_enabled": True,
                    "max_forward_results": legacy_limit,
                })
        return data

    def get_group_config(self, group_id: int) -> Dict[str, bool]:
        cfg = self._store.load()["groups"].get(str(group_id), {})
        return {"auto_push_enabled": bool(cfg.get("auto_push_enabled", False)),
                "query_enabled": bool(cfg.get("query_enabled", False))}

    def _set_group_enabled(self, group_id: int, key: str, enabled: bool) -> bool:
        def mutate(data):
            cfg = data["groups"].setdefault(str(group_id), self._default_group_config())
            if cfg[key] == enabled:
                return False
            cfg[key] = enabled
            return True
        return bool(self._store.mutate(mutate))

    def set_auto_push_enabled(self, group_id: int, enabled: bool) -> bool:
        return self._set_group_enabled(group_id, "auto_push_enabled", enabled)

    def set_query_enabled(self, group_id: int, enabled: bool) -> bool:
        return self._set_group_enabled(group_id, "query_enabled", enabled)

    def list_auto_push_groups(self) -> list[int]:
        return sorted(int(gid) for gid, cfg in self._store.load()["groups"].items()
                      if str(gid).isdigit() and int(gid) > 0 and cfg["auto_push_enabled"])

    def list_configured_groups(self) -> list[int]:
        return sorted(int(gid) for gid in self._store.load()["groups"]
                      if str(gid).isdigit() and int(gid) > 0)

    def export_group_config(self, group_id: int) -> Dict[str, int]:
        cfg = self._store.load()["groups"].get(str(group_id), {})
        return {"max_forward_results": self._normalize_max_forward_results(
            cfg.get("max_forward_results", DEFAULT_MAX_FORWARD_RESULTS)
        )}

    def update_group_config(self, group_id: int, changes: Dict[str, Any]) -> Dict[str, int]:
        if int(group_id) <= 0 or not isinstance(changes, dict) or set(changes) != {"max_forward_results"}:
            raise ValueError("invalid_pig_group_config")
        value = changes["max_forward_results"]
        if type(value) is not int or value < 1:
            raise ValueError("invalid_max_forward_results")
        def mutate(data):
            cfg = data["groups"].setdefault(str(group_id), self._default_group_config())
            cfg["max_forward_results"] = value
            return {"max_forward_results": value}
        return self._store.mutate(mutate)

    def get_max_forward_results(self, group_id: int) -> int:
        return self.export_group_config(group_id)["max_forward_results"]


pig_data_manager = DataManager()
