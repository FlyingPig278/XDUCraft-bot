"""反撤回插件的存储层。

思路：**所有消息先进缓存，撤回时再固化**。

- 群消息一律以“归一化内容树”的形式写进 SQLite，只保存结构和 URL，不下载任何
  文件——绝大多数消息不会被撤回，提前下载纯属浪费。
- 收到撤回通知时才把这条消息标记为已撤回，并**此时**去下载里面的图片。
  撤回一般发生在发出后两分钟内，QQ 的图片链接那时还没过期；等到用户来查询就
  太晚了，链接大概率已经失效——这正是“图片撤回后看不到”的根因。
- 合并转发在**缓存阶段**就递归展开（``get_forward_msg``），因为转发 ID 在原
  消息被撤回后同样会失效。

内容树的节点形状::

    {"type": "text",    "text": "..."}
    {"type": "image",   "url": "...", "file": "本地文件名或空", "summary": "[图片]"}
    {"type": "face",    "id": "123"}
    {"type": "at",      "qq": "10001", "name": "昵称"}
    {"type": "reply",   "id": "消息号"}
    {"type": "forward", "nodes": [{"name","uin","time","content":[...]}]}
    {"type": "other",   "raw": "[CQ:...]", "summary": "[语音]"}
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence

from nonebot.log import logger

from xducraft_bot.shared.json_store import JsonStore, as_bool, as_int, unique_ints

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_FILE = os.path.join(DATA_DIR, "anti_recall.db")
CONFIG_FILE = os.path.join(DATA_DIR, "anti_recall_config.json")
MEDIA_DIR = os.path.join(DATA_DIR, "media")


def _default_config() -> Dict[str, Any]:
    return {
        # 消息缓存保留时长：只影响“还没被撤回”的消息，撤回记录另有保留期。
        "cache_retention_hours": 48,
        # 撤回记录保留天数。
        "recall_retention_days": 7,
        # 一次查询最多返回多少条。
        "max_query_results": 30,
        # 是否下载并本地保存撤回消息里的图片。
        "save_media": True,
        # 单个文件的下载上限（MB）。
        "max_media_mb": 20,
        # 是否记录机器人自己发的消息被撤回。
        "include_self": False,
        # 免于记录的用户（比如管理员自己不想被存）。
        "exempt_user_ids": [],
    }


def _normalize_config(raw: Any) -> Dict[str, Any]:
    config = _default_config()
    if not isinstance(raw, dict):
        return config

    config["cache_retention_hours"] = as_int(raw.get("cache_retention_hours"), 48, minimum=1, maximum=24 * 30)
    config["recall_retention_days"] = as_int(raw.get("recall_retention_days"), 7, minimum=1, maximum=365)
    config["max_query_results"] = as_int(raw.get("max_query_results"), 30, minimum=1, maximum=100)
    config["save_media"] = as_bool(raw.get("save_media"), True)
    config["max_media_mb"] = as_int(raw.get("max_media_mb"), 20, minimum=1, maximum=200)
    config["include_self"] = as_bool(raw.get("include_self"), False)
    config["exempt_user_ids"] = unique_ints(raw.get("exempt_user_ids"))
    return config


class AntiRecallStore:
    """消息缓存 + 撤回记录。"""

    def __init__(self, db_file: str = DB_FILE, config_file: str = CONFIG_FILE, media_dir: str = MEDIA_DIR):
        self.db_file = db_file
        self.media_dir = media_dir
        self._lock = Lock()
        self._config = JsonStore(config_file, _default_config, _normalize_config)
        self._ensure_storage()

    # --- 基础设施 ---

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_file, timeout=10)
        connection.row_factory = sqlite3.Row
        # WAL 让“写入消息”和“查询撤回”不互相阻塞。
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _ensure_storage(self) -> None:
        os.makedirs(os.path.dirname(self.db_file) or ".", exist_ok=True)
        os.makedirs(self.media_dir, exist_ok=True)

        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cached_messages (
                    message_id  INTEGER NOT NULL,
                    group_id    INTEGER NOT NULL,
                    user_id     INTEGER NOT NULL,
                    sender_name TEXT    NOT NULL DEFAULT '',
                    sent_at     INTEGER NOT NULL,
                    content     TEXT    NOT NULL,
                    PRIMARY KEY (group_id, message_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recalls (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id  INTEGER NOT NULL,
                    group_id    INTEGER NOT NULL,
                    user_id     INTEGER NOT NULL,
                    sender_name TEXT    NOT NULL DEFAULT '',
                    operator_id INTEGER NOT NULL DEFAULT 0,
                    sent_at     INTEGER NOT NULL,
                    recalled_at INTEGER NOT NULL,
                    content     TEXT    NOT NULL,
                    UNIQUE (group_id, message_id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_cached_sent_at ON cached_messages(sent_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_recalls_group_time ON recalls(group_id, recalled_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_recalls_time ON recalls(recalled_at DESC)")
            connection.commit()

    # --- 配置 ---

    def get_config(self) -> Dict[str, Any]:
        return self._config.load()

    def set_config_value(self, key: str, value: Any) -> bool:
        if key not in _default_config():
            return False

        def mutate(config: Dict[str, Any]) -> bool:
            config[key] = value
            return True

        self._config.mutate(mutate)
        return True

    def is_user_exempt(self, user_id: int) -> bool:
        return int(user_id) in set(self.get_config().get("exempt_user_ids", []))

    # --- 消息缓存 ---

    def cache_message(
        self,
        group_id: int,
        message_id: int,
        user_id: int,
        sender_name: str,
        content: Sequence[Dict[str, Any]],
        sent_at: Optional[int] = None,
    ) -> None:
        payload = json.dumps(list(content), ensure_ascii=False)
        timestamp = int(sent_at or time.time())

        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO cached_messages(message_id, group_id, user_id, sender_name, sent_at, content)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id, message_id) DO UPDATE SET
                    content = excluded.content, sender_name = excluded.sender_name
                """,
                (int(message_id), int(group_id), int(user_id), str(sender_name), timestamp, payload),
            )
            connection.commit()

    def take_cached_message(self, group_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """取出缓存的消息（不删除，留给定期清理）。"""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM cached_messages WHERE group_id = ? AND message_id = ?",
                (int(group_id), int(message_id)),
            ).fetchone()

        if row is None:
            return None

        try:
            content = json.loads(row["content"])
        except json.JSONDecodeError:
            content = []

        return {
            "message_id": row["message_id"],
            "group_id": row["group_id"],
            "user_id": row["user_id"],
            "sender_name": row["sender_name"],
            "sent_at": row["sent_at"],
            "content": content if isinstance(content, list) else [],
        }

    # --- 撤回记录 ---

    def record_recall(
        self,
        group_id: int,
        message_id: int,
        user_id: int,
        sender_name: str,
        operator_id: int,
        sent_at: int,
        content: Sequence[Dict[str, Any]],
    ) -> bool:
        """写入一条撤回记录。同一条消息重复上报时返回 False。"""
        payload = json.dumps(list(content), ensure_ascii=False)

        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO recalls
                    (message_id, group_id, user_id, sender_name, operator_id, sent_at, recalled_at, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(message_id), int(group_id), int(user_id), str(sender_name),
                 int(operator_id), int(sent_at), int(time.time()), payload),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_recall_content(self, group_id: int, message_id: int, content: Sequence[Dict[str, Any]]) -> None:
        """图片下载完成后回填本地路径。"""
        payload = json.dumps(list(content), ensure_ascii=False)
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "UPDATE recalls SET content = ? WHERE group_id = ? AND message_id = ?",
                (payload, int(group_id), int(message_id)),
            )
            connection.commit()

    def list_recalls(
        self,
        group_ids: Optional[Sequence[int]] = None,
        limit: int = 30,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按时间倒序列出撤回记录。"""
        query = "SELECT * FROM recalls"
        conditions: List[str] = []
        params: List[Any] = []

        if group_ids is not None:
            if not group_ids:
                return []
            conditions.append(f"group_id IN ({','.join('?' * len(group_ids))})")
            params.extend(int(gid) for gid in group_ids)

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(int(user_id))

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY recalled_at DESC LIMIT ?"
        params.append(max(1, min(self.get_config()["max_query_results"], int(limit))))

        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()

        results = []
        for row in rows:
            try:
                content = json.loads(row["content"])
            except json.JSONDecodeError:
                content = []
            results.append({
                "message_id": row["message_id"],
                "group_id": row["group_id"],
                "user_id": row["user_id"],
                "sender_name": row["sender_name"],
                "operator_id": row["operator_id"],
                "sent_at": row["sent_at"],
                "recalled_at": row["recalled_at"],
                "content": content if isinstance(content, list) else [],
            })
        return results

    def list_recent_recall_groups(self, limit: int = 20) -> List[int]:
        """最近有过撤回的群，用于私聊查询时缩小成员校验范围。"""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT group_id, MAX(recalled_at) AS latest FROM recalls "
                "GROUP BY group_id ORDER BY latest DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [int(row["group_id"]) for row in rows]

    def count_recalls(self, group_id: Optional[int] = None) -> int:
        with closing(self._connect()) as connection:
            if group_id is None:
                row = connection.execute("SELECT COUNT(*) AS total FROM recalls").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS total FROM recalls WHERE group_id = ?", (int(group_id),)
                ).fetchone()
        return int(row["total"] if row else 0)

    def purge_group(self, group_id: int) -> int:
        """清空某个群的全部记录（关闭功能时用）。"""
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM recalls WHERE group_id = ?", (int(group_id),))
            connection.execute("DELETE FROM cached_messages WHERE group_id = ?", (int(group_id),))
            connection.commit()
            return int(cursor.rowcount or 0)

    def purge_user(self, user_id: int) -> int:
        """删掉某个用户的全部记录。"""
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM recalls WHERE user_id = ?", (int(user_id),))
            connection.execute("DELETE FROM cached_messages WHERE user_id = ?", (int(user_id),))
            connection.commit()
            return int(cursor.rowcount or 0)

    # --- 媒体文件 ---

    def media_path(self, url: str, extension: str = ".dat") -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.media_dir, f"{digest}{extension}")

    def cleanup(self) -> Dict[str, int]:
        """按保留策略清理数据库和孤立的媒体文件。"""
        config = self.get_config()
        now = int(time.time())
        cache_cutoff = now - config["cache_retention_hours"] * 3600
        recall_cutoff = now - config["recall_retention_days"] * 86400

        with self._lock, closing(self._connect()) as connection:
            cached_removed = connection.execute(
                "DELETE FROM cached_messages WHERE sent_at < ?", (cache_cutoff,)
            ).rowcount
            recalls_removed = connection.execute(
                "DELETE FROM recalls WHERE recalled_at < ?", (recall_cutoff,)
            ).rowcount
            connection.commit()

            referenced = set()
            for row in connection.execute("SELECT content FROM recalls").fetchall():
                try:
                    referenced.update(_iter_media_files(json.loads(row["content"])))
                except json.JSONDecodeError:
                    continue

        media_removed = 0
        try:
            for name in os.listdir(self.media_dir):
                if name in referenced:
                    continue
                path = os.path.join(self.media_dir, name)
                try:
                    # 留一小时缓冲，避免删掉正在下载/刚写入还没入库的文件。
                    if now - os.path.getmtime(path) < 3600:
                        continue
                    os.unlink(path)
                    media_removed += 1
                except OSError:
                    continue
        except OSError as exc:
            logger.debug("[AntiRecall] 清理媒体目录失败: {}", exc)

        return {
            "cached_removed": max(0, cached_removed),
            "recalls_removed": max(0, recalls_removed),
            "media_removed": media_removed,
        }


def _iter_media_files(content: Any):
    """递归收集内容树里引用到的本地媒体文件名。"""
    if isinstance(content, list):
        for item in content:
            yield from _iter_media_files(item)
    elif isinstance(content, dict):
        file_name = content.get("file")
        if isinstance(file_name, str) and file_name:
            yield os.path.basename(file_name)
        for key in ("nodes", "content"):
            if key in content:
                yield from _iter_media_files(content[key])


store = AntiRecallStore()

__all__ = ["AntiRecallStore", "store", "DATA_DIR", "DB_FILE", "MEDIA_DIR"]
