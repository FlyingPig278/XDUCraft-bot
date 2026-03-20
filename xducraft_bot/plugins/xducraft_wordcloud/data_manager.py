import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional, Set

from nonebot.log import logger

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_DB_FILE = os.path.join(DEFAULT_DATA_DIR, "chat_logs.db")
DEFAULT_CONFIG_FILE = os.path.join(DEFAULT_DATA_DIR, "wordcloud_config.json")


class ChatLogDataManager:
    def __init__(
        self,
        data_dir: Optional[str] = None,
        db_file: Optional[str] = None,
        config_file: Optional[str] = None,
    ):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.db_file = db_file or DEFAULT_DB_FILE
        self.config_file = config_file or DEFAULT_CONFIG_FILE
        self._lock = Lock()
        self._ensure_storage()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        return {
            "enabled_groups": [],
            "ban_user_ids": [],
            "min_word_length": 2,
            "max_words": 200,
            "retention_days": 1095,
            "additional_stopwords": [],
            "footer_subtitle": "",
            "footer_branding_enabled": True,
            "footer_branding_text": "Powered by FlyingPig278",
        }

    def _normalize_config(self, raw: Any) -> Dict[str, Any]:
        cfg = self._default_config()
        if not isinstance(raw, dict):
            return cfg

        groups = raw.get("enabled_groups", [])
        if isinstance(groups, list):
            normalized_groups = []
            seen = set()
            for group_id in groups:
                try:
                    gid = int(group_id)
                except (TypeError, ValueError):
                    continue
                if gid in seen:
                    continue
                normalized_groups.append(gid)
                seen.add(gid)
            cfg["enabled_groups"] = normalized_groups

        ban_user_ids = raw.get("ban_user_ids", raw.get("blacklist_user_ids", []))
        if isinstance(ban_user_ids, list):
            normalized_blacklist = []
            seen = set()
            for user_id in ban_user_ids:
                try:
                    uid = int(user_id)
                except (TypeError, ValueError):
                    continue
                if uid in seen:
                    continue
                normalized_blacklist.append(uid)
                seen.add(uid)
            cfg["ban_user_ids"] = normalized_blacklist

        min_word_length = raw.get("min_word_length", cfg["min_word_length"])
        max_words = raw.get("max_words", cfg["max_words"])
        retention_days = raw.get("retention_days", cfg["retention_days"])
        if isinstance(min_word_length, int):
            cfg["min_word_length"] = max(1, int(min_word_length))
        if isinstance(max_words, int):
            cfg["max_words"] = max(20, int(max_words))
        if isinstance(retention_days, int):
            cfg["retention_days"] = max(30, int(retention_days))

        additional_stopwords = raw.get("additional_stopwords", [])
        if isinstance(additional_stopwords, list):
            cfg["additional_stopwords"] = [str(word).strip().lower() for word in additional_stopwords if str(word).strip()]

        footer_subtitle = raw.get("footer_subtitle", "")
        if isinstance(footer_subtitle, str):
            cfg["footer_subtitle"] = footer_subtitle.strip()

        footer_branding_enabled = raw.get("footer_branding_enabled", cfg["footer_branding_enabled"])
        if isinstance(footer_branding_enabled, bool):
            cfg["footer_branding_enabled"] = footer_branding_enabled

        footer_branding_text = raw.get("footer_branding_text", cfg["footer_branding_text"])
        if isinstance(footer_branding_text, str):
            cfg["footer_branding_text"] = footer_branding_text.strip()

        return cfg

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_storage(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "avatars"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "group_avatar_cache"), exist_ok=True)

        if not os.path.exists(self.config_file):
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._default_config(), f, ensure_ascii=False, indent=4)

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
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = self._default_config()
        return self._normalize_config(raw)

    def save_config(self, config: Dict[str, Any]) -> None:
        normalized = self._normalize_config(config)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=4)

    def get_enabled_groups(self) -> List[int]:
        return self.load_config().get("enabled_groups", [])

    def is_group_enabled(self, group_id: int) -> bool:
        return int(group_id) in set(self.get_enabled_groups())

    def set_group_enabled(self, group_id: int, enabled: bool) -> bool:
        cfg = self.load_config()
        groups = [int(g) for g in cfg.get("enabled_groups", [])]
        gid = int(group_id)

        if enabled and gid in groups:
            return False
        if (not enabled) and gid not in groups:
            return False

        if enabled:
            groups.append(gid)
        else:
            groups = [g for g in groups if g != gid]

        cfg["enabled_groups"] = groups
        self.save_config(cfg)
        return True

    def get_wordcloud_options(self) -> Dict[str, int]:
        cfg = self.load_config()
        return {
            "min_word_length": int(cfg.get("min_word_length", 2)),
            "max_words": int(cfg.get("max_words", 200)),
        }

    def get_ban_user_ids(self) -> List[int]:
        cfg = self.load_config()
        return [int(uid) for uid in cfg.get("ban_user_ids", [])]

    def is_user_banned(self, user_id: int) -> bool:
        return int(user_id) in set(self.get_ban_user_ids())

    def set_user_banned(self, user_id: int, banned: bool) -> bool:
        cfg = self.load_config()
        users = [int(uid) for uid in cfg.get("ban_user_ids", [])]
        uid = int(user_id)

        if banned and uid in users:
            return False
        if (not banned) and uid not in users:
            return False

        if banned:
            users.append(uid)
        else:
            users = [item for item in users if item != uid]

        cfg["ban_user_ids"] = users
        self.save_config(cfg)
        return True

    def get_blacklist_user_ids(self) -> List[int]:
        return self.get_ban_user_ids()

    def is_user_blacklisted(self, user_id: int) -> bool:
        return self.is_user_banned(user_id)

    def set_user_blacklisted(self, user_id: int, blacklisted: bool) -> bool:
        return self.set_user_banned(user_id, blacklisted)

    def get_retention_days(self) -> int:
        cfg = self.load_config()
        return max(30, int(cfg.get("retention_days", 1095)))

    def get_footer_subtitle(self) -> str:
        cfg = self.load_config()
        subtitle = cfg.get("footer_subtitle", "")
        if isinstance(subtitle, str):
            return subtitle.strip()
        return ""

    def get_footer_branding_options(self) -> Dict[str, Any]:
        cfg = self.load_config()
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

    def get_stopwords(self) -> Set[str]:
        words: Set[str] = set()

        # stopwordsiso is a widely used multilingual stopwords corpus.
        try:
            import stopwordsiso as stopwords

            words.update({w.lower() for w in stopwords.stopwords("zh")})
            words.update({w.lower() for w in stopwords.stopwords("en")})
        except Exception as e:
            logger.warning("[WordCloud] Failed to load stopwordsiso: %s", e)

        cfg = self.load_config()
        for w in cfg.get("additional_stopwords", []):
            if isinstance(w, str) and w.strip():
                words.add(w.strip().lower())

        return words


chat_log_data_manager = ChatLogDataManager()

