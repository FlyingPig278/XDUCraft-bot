"""SQLite configuration persistence, distinct from plugin business databases."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from .data_paths import shared_data_dir

T = TypeVar("T")
_DEFAULT_DATABASE = str(shared_data_dir() / "configuration.sqlite3")
_databases: Dict[str, "ConfigDatabase"] = {}
_database_lock = RLock()
_write_identity = ContextVar("configuration_write_identity", default=("plugin", None))


@contextmanager
def config_write_context(actor: str, group_id: Optional[int] = None):
    token = _write_identity.set((actor, group_id))
    try:
        yield
    finally:
        _write_identity.reset(token)


def database(path: Optional[str] = None) -> "ConfigDatabase":
    resolved = os.path.abspath(path or os.environ.get("XDUCRAFT_CONFIG_DB") or _DEFAULT_DATABASE)
    with _database_lock:
        if resolved not in _databases:
            _databases[resolved] = ConfigDatabase(resolved)
        return _databases[resolved]


class ConfigDatabase:
    def __init__(self, path: str):
        self.path = path
        self.lock = RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS config_documents (
                namespace TEXT PRIMARY KEY, value TEXT NOT NULL, revision INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config_values (
                plugin_id TEXT NOT NULL, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
                desired TEXT NOT NULL, applied TEXT NOT NULL, status TEXT NOT NULL,
                error TEXT, revision INTEGER NOT NULL,
                PRIMARY KEY(plugin_id, scope, scope_id)
            );
            CREATE TABLE IF NOT EXISTS plugin_controls (
                plugin_id TEXT NOT NULL, scope_id TEXT NOT NULL, enabled INTEGER NOT NULL,
                revision INTEGER NOT NULL, PRIMARY KEY(plugin_id, scope_id)
            );
            CREATE TABLE IF NOT EXISTS config_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
                actor TEXT NOT NULL, namespace TEXT NOT NULL, scope_id TEXT,
                changed_fields TEXT NOT NULL, outcome TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config_migrations (
                migration_key TEXT PRIMARY KEY, completed_at INTEGER NOT NULL
            );
        """)
        self.connection.commit()

    @contextmanager
    def transaction(self):
        with self.lock, self.connection:
            yield self.connection

    @staticmethod
    def encode(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def audit(connection, namespace: str, fields, outcome: str, *, actor=None, group_id=None):
        contextual_actor, contextual_group = _write_identity.get()
        connection.execute(
            "INSERT INTO config_audit(created_at,actor,namespace,scope_id,changed_fields,outcome) VALUES(?,?,?,?,?,?)",
            (int(time.time()), actor or contextual_actor, namespace,
             str(group_id if group_id is not None else contextual_group) if (group_id is not None or contextual_group is not None) else None,
             json.dumps(sorted(set(fields)), ensure_ascii=False), outcome),
        )

    def read_values(self, plugin_id: str, scope: str, scope_id: Optional[int] = None) -> dict:
        with self.lock:
            row = self.connection.execute(
                "SELECT desired,applied,status,error,revision FROM config_values WHERE plugin_id=? AND scope=? AND scope_id=?",
                (plugin_id, scope, "" if scope_id is None else str(scope_id)),
            ).fetchone()
        if row is None:
            return {"desired": {}, "applied": {}, "status": "active", "error": None, "revision": 0}
        return {"desired": json.loads(row["desired"]), "applied": json.loads(row["applied"]),
                "status": row["status"], "error": row["error"], "revision": row["revision"]}

    def write_values(self, plugin_id: str, scope: str, scope_id: Optional[int], *,
                     desired: dict, applied: dict, status: str, error=None,
                     fields=(), actor="plugin") -> dict:
        identifier = "" if scope_id is None else str(scope_id)
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO config_values(plugin_id,scope,scope_id,desired,applied,status,error,revision) "
                "VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(plugin_id,scope,scope_id) DO UPDATE SET "
                "desired=excluded.desired,applied=excluded.applied,status=excluded.status,error=excluded.error,revision=revision+1",
                (plugin_id, scope, identifier, self.encode(desired), self.encode(applied), status, error),
            )
            self.audit(connection, plugin_id, fields, status, actor=actor, group_id=scope_id)
        return self.read_values(plugin_id, scope, scope_id)

    def prepare_native_groups(self, plugin_id: str, defaults: dict, group_fields, known_fields) -> None:
        """Freeze legacy group-effective values once, then seed new groups from code defaults.

        Before the independent-snapshot cutover, a group's sparse row inherited
        mutable values from the global row.  Existing group rows and controls are
        materialized while the migration marker is absent.  Once marked, groups
        first seen later receive only the model's declared defaults.
        """
        fields = set(group_fields)
        baseline = {key: deepcopy(value) for key, value in defaults.items() if key in fields}
        known = set(known_fields)
        migration_key = "native_group_snapshots_v1:" + plugin_id
        with self.transaction() as connection:
            migrated = connection.execute(
                "SELECT 1 FROM config_migrations WHERE migration_key=?", (migration_key,)
            ).fetchone()
            if migrated is not None:
                return
            root_row = connection.execute(
                "SELECT desired,applied FROM config_values "
                "WHERE plugin_id=? AND scope='global' AND scope_id=''",
                (plugin_id,),
            ).fetchone()
            root_desired = json.loads(root_row["desired"]) if root_row is not None else {}
            root_applied = json.loads(root_row["applied"]) if root_row is not None else {}
            group_rows = connection.execute(
                "SELECT scope_id FROM config_values WHERE scope='group' "
                "UNION SELECT scope_id FROM plugin_controls WHERE scope_id!=''",
            ).fetchall()
            groups = {str(row[0]) for row in group_rows}
            feature_document = connection.execute(
                "SELECT value FROM config_documents WHERE namespace='feature_gate'"
            ).fetchone()
            if feature_document is not None:
                try:
                    feature_state = json.loads(feature_document["value"])
                    feature_groups = feature_state.get("groups", {}) if isinstance(feature_state, dict) else {}
                    if isinstance(feature_groups, dict):
                        groups.update(str(group_id) for group_id in feature_groups)
                except (TypeError, ValueError):
                    pass
            identifiers = set()
            for group_id in groups:
                try:
                    numeric_id = int(group_id)
                except (TypeError, ValueError):
                    continue
                if numeric_id > 0:
                    identifiers.add(str(numeric_id))
            for identifier in sorted(identifiers, key=int):
                old = connection.execute(
                    "SELECT desired,applied,status,error FROM config_values "
                    "WHERE plugin_id=? AND scope='group' AND scope_id=?",
                    (plugin_id, identifier),
                ).fetchone()
                old_desired = json.loads(old["desired"]) if old is not None else {}
                old_applied = json.loads(old["applied"]) if old is not None else {}
                legacy_desired = {
                    key: value for key, value in old_desired.items()
                    if key in fields or key not in known
                }
                legacy_applied = {
                    key: value for key, value in old_applied.items()
                    if key in fields or key not in known
                }
                desired = deepcopy(baseline)
                desired.update({key: value for key, value in root_desired.items() if key in fields})
                desired.update(legacy_desired)
                applied = deepcopy(baseline)
                applied.update({key: value for key, value in root_applied.items() if key in fields})
                applied.update(legacy_applied)
                status = old["status"] if old is not None else "active"
                error = old["error"] if old is not None else None
                connection.execute(
                    "INSERT INTO config_values(plugin_id,scope,scope_id,desired,applied,status,error,revision) "
                    "VALUES(?, 'group', ?, ?, ?, ?, ?, 1) "
                    "ON CONFLICT(plugin_id,scope,scope_id) DO UPDATE SET "
                    "desired=excluded.desired,applied=excluded.applied,revision=revision+1",
                    (plugin_id, identifier, self.encode(desired), self.encode(applied), status, error),
                )
                self.audit(
                    connection, plugin_id, fields, "materialized",
                    actor="migration", group_id=int(identifier),
                )
            connection.execute(
                "INSERT INTO config_migrations(migration_key,completed_at) VALUES(?,?)",
                (migration_key, int(time.time())),
            )

    def ensure_native_group(self, plugin_id: str, group_id: int, defaults: dict) -> dict:
        """Atomically create or extend an independent row from code defaults."""
        identifier = str(group_id)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT desired,applied FROM config_values "
                "WHERE plugin_id=? AND scope='group' AND scope_id=?",
                (plugin_id, identifier),
            ).fetchone()
            if row is None:
                encoded = self.encode(deepcopy(defaults))
                connection.execute(
                    "INSERT INTO config_values"
                    "(plugin_id,scope,scope_id,desired,applied,status,error,revision) "
                    "VALUES(?, 'group', ?, ?, ?, 'active', NULL, 1)",
                    (plugin_id, identifier, encoded, encoded),
                )
            else:
                desired, applied = json.loads(row["desired"]), json.loads(row["applied"])
                updated_desired, updated_applied = dict(desired), dict(applied)
                for key, value in defaults.items():
                    updated_desired.setdefault(key, deepcopy(value))
                    updated_applied.setdefault(key, deepcopy(value))
                if updated_desired != desired or updated_applied != applied:
                    connection.execute(
                        "UPDATE config_values SET desired=?,applied=?,revision=revision+1 "
                        "WHERE plugin_id=? AND scope='group' AND scope_id=?",
                        (
                            self.encode(updated_desired), self.encode(updated_applied),
                            plugin_id, identifier,
                        ),
                    )
        return self.read_values(plugin_id, "group", group_id)

    def list_groups(self, plugin_id: str):
        with self.lock:
            rows = self.connection.execute(
                "SELECT scope_id FROM config_values WHERE plugin_id=? AND scope='group' "
                "UNION SELECT scope_id FROM plugin_controls WHERE plugin_id=? AND scope_id!=''",
                (plugin_id, plugin_id),
            ).fetchall()
        return sorted(int(row[0]) for row in rows)

    def list_control_groups(self):
        with self.lock:
            rows = self.connection.execute(
                "SELECT DISTINCT scope_id FROM plugin_controls WHERE scope_id!=''",
            ).fetchall()
        return sorted(int(row[0]) for row in rows)

    def list_known_groups(self):
        with self.lock:
            rows = self.connection.execute(
                "SELECT scope_id FROM config_values WHERE scope='group' "
                "UNION SELECT scope_id FROM plugin_controls WHERE scope_id!=''",
            ).fetchall()
        groups = set()
        for row in rows:
            try:
                group_id = int(row[0])
            except (TypeError, ValueError):
                continue
            if group_id > 0:
                groups.add(group_id)
        return sorted(groups)

    def materialize_feature_controls(
        self, plugin_id: str, feature_key: str, enabled_groups
    ) -> None:
        """Preserve sole-feature ON preferences without enabling the global total."""
        migration_key = "sole_feature_controls_v1:" + plugin_id + ":" + feature_key
        group_ids = set()
        for group_id in enabled_groups:
            try:
                numeric_id = int(group_id)
            except (TypeError, ValueError):
                continue
            if numeric_id > 0:
                group_ids.add(numeric_id)
        with self.transaction() as connection:
            migrated = connection.execute(
                "SELECT 1 FROM config_migrations WHERE migration_key=?", (migration_key,)
            ).fetchone()
            if migrated is not None:
                return
            for group_id in sorted(group_ids):
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO plugin_controls"
                    "(plugin_id,scope_id,enabled,revision) VALUES(?,?,1,1)",
                    (plugin_id, str(group_id)),
                )
                if cursor.rowcount:
                    self.audit(
                        connection, plugin_id, ["plugin_enabled"], "materialized",
                        actor="migration", group_id=group_id,
                    )
            connection.execute(
                "INSERT INTO config_migrations(migration_key,completed_at) VALUES(?,?)",
                (migration_key, int(time.time())),
            )

    def control(self, plugin_id: str, group_id: Optional[int] = None) -> dict:
        with self.lock:
            global_row = self.connection.execute(
                "SELECT enabled,revision FROM plugin_controls WHERE plugin_id=? AND scope_id=''", (plugin_id,)
            ).fetchone()
            group_row = self.connection.execute(
                "SELECT enabled,revision FROM plugin_controls WHERE plugin_id=? AND scope_id=?",
                (plugin_id, str(group_id)),
            ).fetchone() if group_id is not None else None
        root = bool(global_row[0]) if global_row is not None else False
        enabled = root if group_id is None else (
            bool(group_row[0]) if group_row is not None else False
        )
        return {"enabled": enabled,
                "source": "group" if group_row is not None else "default",
                "raw": [tuple(global_row) if global_row is not None else None,
                        tuple(group_row) if group_row is not None else None]}

    def set_control(self, plugin_id: str, group_id: Optional[int], enabled: bool):
        identifier = "" if group_id is None else str(group_id)
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO plugin_controls(plugin_id,scope_id,enabled,revision) VALUES(?,?,?,1) "
                "ON CONFLICT(plugin_id,scope_id) DO UPDATE SET enabled=excluded.enabled,revision=revision+1",
                (plugin_id, identifier, int(enabled)),
            )
            self.audit(connection, plugin_id, ["plugin_enabled"], "active", group_id=group_id)
        return self.control(plugin_id, group_id)


class ConfigDocumentStore(Generic[T]):
    """Atomic plugin configuration documents with a strict one-time JSON import.

    Legacy files are import inputs only. Once a namespace exists, all reads and
    writes use SQLite; changing an old JSON file never becomes a second writer.
    Normalizers preserve existing manager semantics during progressive cutover.
    """
    def __init__(self, namespace: str, default_factory: Callable[[], T],
                 normalizer: Optional[Callable[[Any], T]] = None, *,
                 legacy_path: Optional[str] = None, allow_comments: bool = False,
                 database_path: Optional[str] = None):
        self.namespace = namespace
        self._default_factory = default_factory
        self._normalizer = normalizer
        self.legacy_path = legacy_path
        self._allow_comments = allow_comments
        self.database_path = database_path

    @property
    def path(self) -> str:
        return database(self.database_path).path

    def _normalize(self, value) -> T:
        return self._normalizer(value) if self._normalizer is not None else value

    def _initial(self) -> T:
        if not self.legacy_path or not os.path.exists(self.legacy_path):
            return self._normalize(self._default_factory())
        text = Path(self.legacy_path).read_text(encoding="utf-8")
        if self._allow_comments:
            text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
        if not text.strip():
            raise ValueError("empty legacy configuration: " + self.namespace)
        return self._normalize(json.loads(text))

    def _load(self, connection, db) -> T:
        row = connection.execute("SELECT value FROM config_documents WHERE namespace=?", (self.namespace,)).fetchone()
        if row is not None:
            stored = json.loads(row[0])
            return self._save(connection, db, stored, stored, outcome="migrated")
        value = self._initial()
        connection.execute("INSERT INTO config_documents(namespace,value,revision) VALUES(?,?,1)",
                           (self.namespace, db.encode(value)))
        db.audit(connection, self.namespace, value.keys() if isinstance(value, dict) else [], "migrated")
        return value

    def load(self) -> T:
        db = database(self.database_path)
        with db.transaction() as connection:
            return deepcopy(self._load(connection, db))

    def _save(self, connection, db, old, value, *, outcome="active"):
        normalized = self._normalize(value)
        if normalized != old:
            connection.execute(
                "UPDATE config_documents SET value=?,revision=revision+1 WHERE namespace=?",
                (db.encode(normalized), self.namespace),
            )
            fields = [key for key in set(old) | set(normalized) if old.get(key) != normalized.get(key)] if isinstance(old, dict) and isinstance(normalized, dict) else []
            db.audit(connection, self.namespace, fields, outcome, actor="migration" if outcome == "migrated" else None)
        return normalized

    def save(self, value: T) -> T:
        db = database(self.database_path)
        with db.transaction() as connection:
            old = self._load(connection, db)
            return deepcopy(self._save(connection, db, old, value))

    def mutate(self, mutator: Callable[[T], Any]) -> Any:
        db = database(self.database_path)
        with db.transaction() as connection:
            old = self._load(connection, db)
            candidate = deepcopy(old)
            result = mutator(candidate)
            self._save(connection, db, old, candidate)
            return result



def close_databases() -> None:
    """Release process-owned connections during shutdown and isolated smoke runs."""
    with _database_lock:
        for db in _databases.values():
            with db.lock:
                db.connection.close()
        _databases.clear()
