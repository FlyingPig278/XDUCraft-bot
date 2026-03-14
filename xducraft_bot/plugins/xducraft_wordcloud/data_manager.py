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
            "min_word_length": 2,
            "max_words": 200,
            "retention_days": 1095,
            "additional_stopwords": [],
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

        return cfg

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_storage(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)

        if not os.path.exists(self.config_file):
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._default_config(), f, ensure_ascii=False, indent=4)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    chat_date TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_group_date ON chat_logs(group_id, chat_date)")
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

    def get_retention_days(self) -> int:
        cfg = self.load_config()
        return max(30, int(cfg.get("retention_days", 1095)))

    def add_message(self, group_id: int, message: str, created_at: Optional[int] = None) -> None:
        clean = (message or "").strip()
        if not clean:
            return

        ts = int(created_at or datetime.now().timestamp())
        d = datetime.fromtimestamp(ts).date().isoformat()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO chat_logs(group_id, chat_date, message, created_at) VALUES (?, ?, ?, ?)",
                    (int(group_id), d, clean, ts),
                )
                conn.commit()

    def get_messages_for_date(self, group_id: int, target_date: date) -> List[str]:
        d = target_date.isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message FROM chat_logs WHERE group_id = ? AND chat_date = ? ORDER BY id ASC",
                (int(group_id), d),
            ).fetchall()
        return [str(row["message"]) for row in rows]

    def get_messages_for_month(self, group_id: int, year: int, month: int) -> List[str]:
        month_prefix = f"{year:04d}-{month:02d}"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message FROM chat_logs WHERE group_id = ? AND chat_date LIKE ? ORDER BY id ASC",
                (int(group_id), f"{month_prefix}%"),
            ).fetchall()
        return [str(row["message"]) for row in rows]

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

