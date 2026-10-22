import os
import sqlite3
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional, Set

from nonebot.log import logger

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.config_store import ConfigDocumentStore
from xducraft_bot.shared.data_paths import plugin_data_dir

DEFAULT_DATA_DIR = str(plugin_data_dir("wordcloud", os.path.join(os.path.dirname(__file__), "data")))
DEFAULT_DB_FILE = os.path.join(DEFAULT_DATA_DIR, "chat_logs.db")
DEFAULT_CONFIG_FILE = os.path.join(DEFAULT_DATA_DIR, "wordcloud_config.json")

GROUP_CONFIG_KEYS = (
    "ban_user_ids",
    "min_word_length",
    "max_words",
    "additional_stopwords",
    "footer_subtitle",
    "footer_branding_enabled",
    "footer_branding_text",
)

GROUP_VALUE_DEFAULTS = {
    "ban_user_ids": [],
    "min_word_length": 2,
    "max_words": 200,
    "additional_stopwords": [],
    "footer_subtitle": "",
    "footer_branding_enabled": True,
    "footer_branding_text": "Powered by FlyingPig278",
}


class ChatLogDataManager:
    def __init__(
        self,
        data_dir: Optional[str] = None,
        db_file: Optional[str] = None,
        *,
        legacy_config_path: Optional[str] = None,
        configuration_db_path: Optional[str] = None,
    ):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.db_file = db_file or DEFAULT_DB_FILE
        self._config_store = ConfigDocumentStore(
            "wordcloud", self._default_config, self._normalize_config,
            legacy_path=legacy_config_path or DEFAULT_CONFIG_FILE,
            database_path=configuration_db_path,
        )
        self._lock = Lock()
        self._ensure_storage()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        return {
            "schema_version": 2,
            "enabled_groups": [],
            "ban_user_ids": [],
            "retention_days": 1095,
            "groups": {},
        }

    @staticmethod
    def _normalize_ids(value: Any) -> List[int]:
        if not isinstance(value, list):
            raise ValueError("wordcloud_user_ids_must_be_list")
        normalized: List[int] = []
        seen: Set[int] = set()
        for item in value:
            try:
                item_id = int(item)
            except (TypeError, ValueError):
                continue
            if item_id in seen:
                continue
            normalized.append(item_id)
            seen.add(item_id)
        return normalized

    @staticmethod
    def _normalize_stopwords(value: Any) -> List[str]:
        if not isinstance(value, list):
            raise ValueError("wordcloud_stopwords_must_be_list")
        return [str(word).strip().lower() for word in value if str(word).strip()]

    @classmethod
    def _normalize_group_value(cls, key: str, value: Any) -> Any:
        if key == "ban_user_ids":
            return cls._normalize_ids(value)
        if key == "additional_stopwords":
            return cls._normalize_stopwords(value)
        if key == "min_word_length" and isinstance(value, int):
            return max(1, int(value))
        if key == "max_words" and isinstance(value, int):
            return max(20, int(value))
        if key in {"footer_subtitle", "footer_branding_text"} and isinstance(value, str):
            return value.strip()
        if key == "footer_branding_enabled" and isinstance(value, bool):
            return value
        raise ValueError("invalid_wordcloud_group_config_value")

    def _normalize_config(self, raw: Any) -> Dict[str, Any]:
        cfg = self._default_config()
        if not isinstance(raw, dict):
            raise ValueError("wordcloud_config_must_be_object")

        groups = raw.get("enabled_groups", [])
        if isinstance(groups, list):
            cfg["enabled_groups"] = list(dict.fromkeys(
                gid for gid in (int(value) for value in groups if str(value).lstrip("-").isdigit())
                if gid > 0
            ))

        try:
            cfg["ban_user_ids"] = self._normalize_ids(
                raw.get("ban_user_ids", raw.get("blacklist_user_ids", []))
            )
        except ValueError:
            pass
        retention_days = raw.get("retention_days", cfg["retention_days"])
        if isinstance(retention_days, int):
            cfg["retention_days"] = max(30, int(retention_days))

        legacy = raw.get("schema_version") != 2
        raw_groups = raw.get("group_overrides", {}) if legacy else raw.get("groups", {})
        known_groups = set(cfg["enabled_groups"])
        if legacy:
            known_groups.update(feature_gate.list_configured_groups())
        if isinstance(raw_groups, dict):
            for raw_group_id in raw_groups:
                try:
                    gid = int(raw_group_id)
                except (TypeError, ValueError):
                    continue
                if gid > 0:
                    known_groups.add(gid)

        legacy_defaults = dict(GROUP_VALUE_DEFAULTS)
        if legacy:
            for key in GROUP_CONFIG_KEYS:
                if key == "ban_user_ids":
                    continue
                if key in raw:
                    try:
                        legacy_defaults[key] = self._normalize_group_value(key, raw[key])
                    except ValueError:
                        pass

        for gid in known_groups:
            source = raw_groups.get(str(gid), raw_groups.get(gid, {})) if isinstance(raw_groups, dict) else {}
            source = source if isinstance(source, dict) else {}
            values: Dict[str, Any] = {}
            for key, fallback in GROUP_VALUE_DEFAULTS.items():
                effective_fallback = legacy_defaults[key] if legacy else fallback
                raw_value = source.get(key, effective_fallback)
                try:
                    values[key] = self._normalize_group_value(key, raw_value)
                except ValueError:
                    values[key] = list(effective_fallback) if isinstance(effective_fallback, list) else effective_fallback
            cfg["groups"][str(gid)] = values
        return cfg

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_storage(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "avatars"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "group_avatar_cache"), exist_ok=True)

        self._config_store.load()

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    user_id INTEGER,
                    chat_date TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    message_id INTEGER
                )
                """
            )
            table_info = conn.execute("PRAGMA table_info(chat_logs)").fetchall()
            existing_columns = {str(row[1]) for row in table_info}
            if "user_id" not in existing_columns:
                conn.execute("ALTER TABLE chat_logs ADD COLUMN user_id INTEGER")
            if "message_id" not in existing_columns:
                conn.execute("ALTER TABLE chat_logs ADD COLUMN message_id INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_group_date ON chat_logs(group_id, chat_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_group_message_id ON chat_logs(group_id, message_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_group_user ON chat_logs(group_id, user_id)")
            conn.commit()

    def load_config(self) -> Dict[str, Any]:
        return self._config_store.load()

    def save_config(self, config: Dict[str, Any]) -> None:
        self._config_store.save(config)

    def get_enabled_groups(self) -> List[int]:
        return self.load_config().get("enabled_groups", [])

    def list_configured_groups(self) -> List[int]:
        cfg = self.load_config()
        groups = {int(group_id) for group_id in cfg.get("enabled_groups", []) if int(group_id) > 0}
        groups.update(int(group_id) for group_id in cfg.get("groups", {}) if int(group_id) > 0)
        return sorted(groups)

    def is_group_enabled(self, group_id: int) -> bool:
        return int(group_id) in set(self.get_enabled_groups())

    def set_group_enabled(self, group_id: int, enabled: bool) -> bool:
        gid = int(group_id)

        def mutate(cfg: Dict[str, Any]) -> bool:
            groups = [int(g) for g in cfg.get("enabled_groups", [])]
            if enabled and gid in groups:
                return False
            if (not enabled) and gid not in groups:
                return False
            if enabled:
                groups.append(gid)
            else:
                groups = [g for g in groups if g != gid]
            cfg["enabled_groups"] = groups
            return True

        return bool(self._config_store.mutate(mutate))

    @staticmethod
    def _export_group_config_from(cfg: Dict[str, Any], group_id: int) -> Dict[str, Any]:
        values = cfg.get("groups", {}).get(str(int(group_id)), {})
        if not isinstance(values, dict):
            values = {}
        return {
            key: values.get(key, list(default) if isinstance(default, list) else default)
            for key, default in GROUP_VALUE_DEFAULTS.items()
        }

    def export_group_config(self, group_id: int) -> Dict[str, Any]:
        return self._export_group_config_from(self.load_config(), group_id)

    def get_effective_group_config(self, group_id: int) -> Dict[str, Any]:
        cfg = self.load_config()
        effective = self._export_group_config_from(cfg, group_id)
        global_bans = [int(item) for item in cfg.get("ban_user_ids", [])]
        local_bans = [int(item) for item in effective["ban_user_ids"]]
        effective["ban_user_ids"] = list(dict.fromkeys([*global_bans, *local_bans]))
        return effective

    def update_group_config(self, group_id: int, changes: Dict[str, Any]) -> Dict[str, Any]:
        gid = int(group_id)
        if gid <= 0:
            raise ValueError("wordcloud_group_id_must_be_positive")
        if not isinstance(changes, dict):
            raise ValueError("wordcloud_group_config_must_be_object")
        unknown = set(changes) - set(GROUP_CONFIG_KEYS)
        if unknown:
            raise ValueError("unknown_wordcloud_group_config_key")

        normalized_changes: Dict[str, Any] = {}
        for key, value in changes.items():
            if value is None:
                raise ValueError("wordcloud_group_values_must_be_direct")
            normalized_changes[key] = self._normalize_group_value(key, value)
        if set(normalized_changes) != set(GROUP_CONFIG_KEYS):
            raise ValueError("wordcloud_group_config_incomplete")

        def mutate(cfg: Dict[str, Any]) -> Dict[str, Any]:
            cfg.setdefault("groups", {})[str(gid)] = normalized_changes
            return self._export_group_config_from(cfg, gid)

        return self._config_store.mutate(mutate)

    def get_wordcloud_options(self, group_id: Optional[int] = None) -> Dict[str, int]:
        cfg = self.load_config() if group_id is None else self.get_effective_group_config(group_id)
        return {
            "min_word_length": int(cfg.get("min_word_length", 2)),
            "max_words": int(cfg.get("max_words", 200)),
        }

    def get_ban_user_ids(self, group_id: Optional[int] = None) -> List[int]:
        cfg = self.load_config() if group_id is None else self.get_effective_group_config(group_id)
        return [int(uid) for uid in cfg.get("ban_user_ids", [])]

    def get_group_ban_user_ids(self, group_id: int) -> List[int]:
        return [int(uid) for uid in (self.export_group_config(group_id).get("ban_user_ids") or [])]

    def is_user_banned(self, user_id: int, group_id: Optional[int] = None) -> bool:
        return int(user_id) in set(self.get_ban_user_ids(group_id))

    def set_user_banned(self, user_id: int, banned: bool) -> bool:
        uid = int(user_id)

        def mutate(cfg: Dict[str, Any]) -> bool:
            users = [int(item) for item in cfg.get("ban_user_ids", [])]
            if banned and uid in users:
                return False
            if (not banned) and uid not in users:
                return False
            if banned:
                users.append(uid)
            else:
                users = [item for item in users if item != uid]
            cfg["ban_user_ids"] = users
            return True

        return bool(self._config_store.mutate(mutate))

    def set_group_user_banned(self, group_id: int, user_id: int, banned: bool) -> bool:
        gid = int(group_id)
        if gid <= 0:
            raise ValueError("wordcloud_group_id_must_be_positive")
        uid = int(user_id)

        def mutate(cfg: Dict[str, Any]) -> bool:
            groups = cfg.setdefault("groups", {})
            current = self._export_group_config_from(cfg, gid)
            users = [int(item) for item in current["ban_user_ids"]]
            if banned and uid in users:
                return False
            if (not banned) and uid not in users:
                return False
            current["ban_user_ids"] = (
                [*users, uid] if banned else [item for item in users if item != uid]
            )
            groups[str(gid)] = current
            return True

        return bool(self._config_store.mutate(mutate))

    def update_global_config(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically update global retention and safety policy."""
        allowed = {"ban_user_ids", "retention_days"}
        if not isinstance(changes, dict) or set(changes) != allowed:
            raise ValueError("wordcloud_global_config_incomplete")

        def mutate(cfg: Dict[str, Any]) -> Dict[str, Any]:
            candidate = dict(cfg)
            candidate.update(changes)
            normalized = self._normalize_config(candidate)
            for key in allowed:
                cfg[key] = normalized[key]
            return {key: cfg[key] for key in allowed}

        return self._config_store.mutate(mutate)


    def get_blacklist_user_ids(self, group_id: Optional[int] = None) -> List[int]:
        return self.get_ban_user_ids(group_id)

    def is_user_blacklisted(self, user_id: int, group_id: Optional[int] = None) -> bool:
        return self.is_user_banned(user_id, group_id)

    def set_user_blacklisted(self, user_id: int, blacklisted: bool) -> bool:
        return self.set_user_banned(user_id, blacklisted)

    def get_retention_days(self) -> int:
        cfg = self.load_config()
        return max(30, int(cfg.get("retention_days", 1095)))

    def get_footer_subtitle(self, group_id: Optional[int] = None) -> str:
        cfg = self.load_config() if group_id is None else self.get_effective_group_config(group_id)
        subtitle = cfg.get("footer_subtitle", "")
        if isinstance(subtitle, str):
            return subtitle.strip()
        return ""

    def get_footer_branding_options(self, group_id: Optional[int] = None) -> Dict[str, Any]:
        cfg = self.load_config() if group_id is None else self.get_effective_group_config(group_id)
        enabled = cfg.get("footer_branding_enabled", True)
        text = cfg.get("footer_branding_text", "Powered by FlyingPig278")
        return {
            "enabled": bool(enabled),
            "text": str(text).strip(),
        }

    def add_message(
        self,
        group_id: int,
        message: str,
        created_at: Optional[int] = None,
        message_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> None:
        clean = (message or "").strip()
        if not clean:
            return

        ts = int(created_at or datetime.now().timestamp())
        d = datetime.fromtimestamp(ts).date().isoformat()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO chat_logs(group_id, user_id, chat_date, message, created_at, message_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        int(group_id),
                        int(user_id) if user_id is not None else None,
                        d,
                        clean,
                        ts,
                        int(message_id) if message_id is not None else None,
                    ),
                )
                conn.commit()

    def delete_message_by_message_id(self, group_id: int, message_id: int) -> int:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM chat_logs WHERE group_id = ? AND message_id = ?",
                    (int(group_id), int(message_id)),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def delete_messages_by_user_id(self, group_id: int, user_id: int) -> int:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM chat_logs WHERE group_id = ? AND user_id = ?",
                    (int(group_id), int(user_id)),
                )
                conn.commit()
                return int(cursor.rowcount or 0)

    def get_messages_for_date(
        self,
        group_id: int,
        target_date: date,
        excluded_user_ids: Optional[Set[int]] = None,
    ) -> List[str]:
        d = target_date.isoformat()
        excluded = {int(uid) for uid in (excluded_user_ids or set())}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message, user_id FROM chat_logs WHERE group_id = ? AND chat_date = ? ORDER BY id ASC",
                (int(group_id), d),
            ).fetchall()
        output: List[str] = []
        for row in rows:
            row_user_id = row["user_id"]
            if row_user_id is not None and int(row_user_id) in excluded:
                continue
            output.append(str(row["message"]))
        return output

    def get_messages_for_month(
        self,
        group_id: int,
        year: int,
        month: int,
        excluded_user_ids: Optional[Set[int]] = None,
    ) -> List[str]:
        month_prefix = f"{year:04d}-{month:02d}"
        excluded = {int(uid) for uid in (excluded_user_ids or set())}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message, user_id FROM chat_logs WHERE group_id = ? AND chat_date LIKE ? ORDER BY id ASC",
                (int(group_id), f"{month_prefix}%"),
            ).fetchall()
        output: List[str] = []
        for row in rows:
            row_user_id = row["user_id"]
            if row_user_id is not None and int(row_user_id) in excluded:
                continue
            output.append(str(row["message"]))
        return output

    def get_messages_for_group(self, group_id: int, excluded_user_ids: Optional[Set[int]] = None) -> List[str]:
        excluded = {int(uid) for uid in (excluded_user_ids or set())}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message, user_id FROM chat_logs WHERE group_id = ? ORDER BY id ASC",
                (int(group_id),),
            ).fetchall()
        output: List[str] = []
        for row in rows:
            row_user_id = row["user_id"]
            if row_user_id is not None and int(row_user_id) in excluded:
                continue
            output.append(str(row["message"]))
        return output

    def cleanup_old_messages(self, keep_days: int = 3, ref_date: Optional[date] = None) -> int:
        base = ref_date or date.today()
        cutoff = (base - timedelta(days=max(1, keep_days) - 1)).isoformat()

        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM chat_logs WHERE chat_date < ?", (cutoff,))
                conn.commit()
                return int(cursor.rowcount or 0)

    def get_stopwords(self, group_id: Optional[int] = None) -> Set[str]:
        words: Set[str] = set()

        # stopwordsiso is a widely used multilingual stopwords corpus.
        try:
            import stopwordsiso as stopwords

            words.update({w.lower() for w in stopwords.stopwords("zh")})
            words.update({w.lower() for w in stopwords.stopwords("en")})
        except Exception as e:
            logger.warning("[WordCloud] Failed to load stopwordsiso: %s", e)

        cfg = self.load_config() if group_id is None else self.get_effective_group_config(group_id)
        for w in cfg.get("additional_stopwords", []):
            if isinstance(w, str) and w.strip():
                words.add(w.strip().lower())

        return words


chat_log_data_manager = ChatLogDataManager()

