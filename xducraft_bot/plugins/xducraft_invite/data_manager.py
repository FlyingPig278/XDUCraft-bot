"""邀请码资格、旧成员快照和并发占用的 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from threading import Lock
from typing import Iterable, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_FILE = os.path.join(DATA_DIR, "invitations.db")
LEASE_TTL_SECONDS = 180

ACQUIRED = "acquired"
ALREADY_CLAIMED = "already_claimed"
IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class InviteState:
    initialized_at: Optional[int]
    initialized_by: Optional[int]
    self_service_enabled: bool

    @property
    def initialized(self) -> bool:
        return self.initialized_at is not None


@dataclass(frozen=True)
class InviteStats:
    state: InviteState
    legacy_count: int
    claimed_count: int
    issuance_count: int


class InviteStore:
    def __init__(self, db_file: str = DB_FILE) -> None:
        self.db_file = os.path.abspath(db_file)
        self._lock = Lock()
        self._ensure_storage()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_file, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _ensure_storage(self) -> None:
        os.makedirs(os.path.dirname(self.db_file) or ".", exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS invite_state (
                    id                   INTEGER PRIMARY KEY CHECK (id = 1),
                    initialized_at       INTEGER,
                    initialized_by       INTEGER,
                    self_service_enabled INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO invite_state(id) VALUES (1);

                CREATE TABLE IF NOT EXISTS legacy_members (
                    user_id     INTEGER PRIMARY KEY,
                    captured_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS claimed_users (
                    user_id          INTEGER PRIMARY KEY,
                    first_source     TEXT    NOT NULL,
                    group_id         INTEGER NOT NULL,
                    operator_id      INTEGER NOT NULL,
                    claimed_at       INTEGER NOT NULL,
                    api_generated_at TEXT    NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS issuance_audit (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id          INTEGER NOT NULL,
                    source           TEXT    NOT NULL,
                    group_id         INTEGER NOT NULL,
                    operator_id      INTEGER NOT NULL,
                    forced           INTEGER NOT NULL DEFAULT 0,
                    issued_at        INTEGER NOT NULL,
                    api_generated_at TEXT    NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_issuance_user_time
                    ON issuance_audit(user_id, issued_at DESC);

                CREATE TABLE IF NOT EXISTS issuance_leases (
                    user_id     INTEGER PRIMARY KEY,
                    source      TEXT    NOT NULL,
                    operator_id INTEGER NOT NULL,
                    started_at  INTEGER NOT NULL
                );
                """
            )
            connection.commit()

    def get_state(self) -> InviteState:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT initialized_at, initialized_by, self_service_enabled FROM invite_state WHERE id = 1"
            ).fetchone()
        return InviteState(
            initialized_at=int(row["initialized_at"]) if row and row["initialized_at"] is not None else None,
            initialized_by=int(row["initialized_by"]) if row and row["initialized_by"] is not None else None,
            self_service_enabled=bool(row["self_service_enabled"]) if row else False,
        )

    def initialize(self, legacy_user_ids: Iterable[int], initialized_at: int, initialized_by: int) -> bool:
        unique_ids = {int(user_id) for user_id in legacy_user_ids if int(user_id) > 0}
        timestamp = int(initialized_at)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT initialized_at FROM invite_state WHERE id = 1"
            ).fetchone()
            if row is not None and row["initialized_at"] is not None:
                connection.rollback()
                return False

            connection.executemany(
                "INSERT OR IGNORE INTO legacy_members(user_id, captured_at) VALUES (?, ?)",
                ((user_id, timestamp) for user_id in unique_ids),
            )
            connection.execute(
                """
                UPDATE invite_state
                SET initialized_at = ?, initialized_by = ?, self_service_enabled = 1
                WHERE id = 1
                """,
                (timestamp, int(initialized_by)),
            )
            connection.commit()
            return True

    def set_self_service_enabled(self, enabled: bool) -> bool:
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT initialized_at, self_service_enabled FROM invite_state WHERE id = 1"
            ).fetchone()
            if row is None or row["initialized_at"] is None:
                connection.rollback()
                return False
            connection.execute(
                "UPDATE invite_state SET self_service_enabled = ? WHERE id = 1",
                (1 if enabled else 0,),
            )
            connection.commit()
            return True

    def is_legacy(self, user_id: int) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM legacy_members WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        return row is not None

    def has_claim(self, user_id: int) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM claimed_users WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        return row is not None

    def acquire_lease(
        self,
        user_id: int,
        *,
        source: str,
        operator_id: int,
        allow_claimed: bool = False,
        now: Optional[int] = None,
    ) -> str:
        timestamp = int(now if now is not None else time.time())
        stale_before = timestamp - LEASE_TTL_SECONDS
        target = int(user_id)

        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM issuance_leases WHERE started_at <= ?",
                (stale_before,),
            )
            active = connection.execute(
                "SELECT 1 FROM issuance_leases WHERE user_id = ?",
                (target,),
            ).fetchone()
            if active is not None:
                connection.rollback()
                return IN_PROGRESS

            if not allow_claimed:
                claimed = connection.execute(
                    "SELECT 1 FROM claimed_users WHERE user_id = ?",
                    (target,),
                ).fetchone()
                if claimed is not None:
                    connection.rollback()
                    return ALREADY_CLAIMED

            connection.execute(
                """
                INSERT INTO issuance_leases(user_id, source, operator_id, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (target, str(source), int(operator_id), timestamp),
            )
            connection.commit()
            return ACQUIRED

    def release_lease(self, user_id: int) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "DELETE FROM issuance_leases WHERE user_id = ?",
                (int(user_id),),
            )
            connection.commit()

    def record_success(
        self,
        user_id: int,
        *,
        source: str,
        group_id: int,
        operator_id: int,
        forced: bool,
        api_generated_at: str,
        issued_at: Optional[int] = None,
    ) -> None:
        timestamp = int(issued_at if issued_at is not None else time.time())
        target = int(user_id)
        with self._lock, closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO claimed_users(
                    user_id, first_source, group_id, operator_id, claimed_at, api_generated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    target,
                    str(source),
                    int(group_id),
                    int(operator_id),
                    timestamp,
                    str(api_generated_at),
                ),
            )
            connection.execute(
                """
                INSERT INTO issuance_audit(
                    user_id, source, group_id, operator_id, forced, issued_at, api_generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target,
                    str(source),
                    int(group_id),
                    int(operator_id),
                    1 if forced else 0,
                    timestamp,
                    str(api_generated_at),
                ),
            )
            connection.execute(
                "DELETE FROM issuance_leases WHERE user_id = ?",
                (target,),
            )
            connection.commit()

    def stats(self) -> InviteStats:
        state = self.get_state()
        with closing(self._connect()) as connection:
            legacy_count = int(connection.execute("SELECT COUNT(*) FROM legacy_members").fetchone()[0])
            claimed_count = int(connection.execute("SELECT COUNT(*) FROM claimed_users").fetchone()[0])
            issuance_count = int(connection.execute("SELECT COUNT(*) FROM issuance_audit").fetchone()[0])
        return InviteStats(
            state=state,
            legacy_count=legacy_count,
            claimed_count=claimed_count,
            issuance_count=issuance_count,
        )


store = InviteStore()


__all__ = [
    "ACQUIRED",
    "ALREADY_CLAIMED",
    "IN_PROGRESS",
    "LEASE_TTL_SECONDS",
    "InviteState",
    "InviteStats",
    "InviteStore",
    "store",
]
