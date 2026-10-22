import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.migrate_runtime_data import (
    MANIFEST_FORMAT,
    MANIFEST_NAME,
    MANIFEST_VERSION,
    MigrationError,
    migrate,
    restore,
)


def _write(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _open_wal_database(path: Path, value: str = "committed-in-wal") -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    assert connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
    connection.commit()
    connection.execute("INSERT INTO records VALUES (?)", (value,))
    connection.commit()
    assert Path(str(path) + "-wal").is_file()
    return connection


def test_migrate_wal_data_preserves_files_is_idempotent_and_restores(tmp_path, monkeypatch):
    monkeypatch.delenv("XDUCRAFT_CONFIG_DB", raising=False)
    legacy = tmp_path / "legacy"
    config_db = legacy / "xducraft_bot/shared/data/configuration.sqlite3"
    connection = _open_wal_database(config_db)
    business_json = b'{"token":"raw-secret-is-preserved","groups":{"42":true}}\n'
    _write(legacy, "xducraft_bot/shared/data/deployment_overrides.json", business_json)
    _write(legacy, "xducraft_bot/shared/data/migrations/old-snapshot.bin", b"historical")
    _write(legacy, "xducraft_bot/plugins/xducraft_wordcloud/data/avatars/user.png", b"avatar")
    _write(legacy, "xducraft_bot/plugins/xducraft_wordcloud/data/images/old.png", b"wordcloud")
    _write(legacy, "xducraft_bot/plugins/xducraft_keyword/data/custom.unknown", b"unknown")
    _write(legacy, "xducraft_bot/plugins/xducraft_mc_status/image_cache/server.png", b"cache")
    snapshot = tmp_path / "snapshot"

    try:
        assert migrate(legacy, snapshot, config_db=config_db) == "migrated"
        copied = sqlite3.connect(str(snapshot / "core/configuration.sqlite3"))
        try:
            assert copied.execute("SELECT value FROM records").fetchall() == [("committed-in-wal",)]
        finally:
            copied.close()
        assert not (snapshot / "core/configuration.sqlite3-wal").exists()
        assert not (snapshot / "core/configuration.sqlite3-shm").exists()
        assert (snapshot / "core/deployment_overrides.json").read_bytes() == business_json
        assert (snapshot / "core/migrations/old-snapshot.bin").read_bytes() == b"historical"
        assert (snapshot / "plugins/wordcloud/avatars/user.png").read_bytes() == b"avatar"
        assert (snapshot / "plugins/wordcloud/images/old.png").read_bytes() == b"wordcloud"
        assert (snapshot / "plugins/keyword/custom.unknown").read_bytes() == b"unknown"
        assert (snapshot / "cache/mc_status/server.png").read_bytes() == b"cache"

        assert migrate(legacy, snapshot, config_db=config_db) == "already-complete"
        original_manifest = (snapshot / MANIFEST_NAME).read_bytes()
        original_target = (snapshot / "plugins/keyword/custom.unknown").read_bytes()
        target_file = snapshot / "plugins/keyword/custom.unknown"
        target_file.write_bytes(b"tampered target")
        with pytest.raises(MigrationError, match="manifest"):
            migrate(legacy, snapshot, config_db=config_db)
        assert target_file.read_bytes() == b"tampered target"
        target_file.write_bytes(original_target)

        _write(legacy, "xducraft_bot/plugins/xducraft_keyword/data/custom.unknown", b"changed")
        with pytest.raises(MigrationError, match="does not match"):
            migrate(legacy, snapshot, config_db=config_db)
        assert (snapshot / MANIFEST_NAME).read_bytes() == original_manifest
        assert target_file.read_bytes() == original_target
    finally:
        connection.close()

    restored = tmp_path / "restored"
    assert restore(snapshot, restored) == "restored"
    restored_db = restored / "xducraft_bot/shared/data/configuration.sqlite3"
    copied = sqlite3.connect(str(restored_db))
    try:
        assert copied.execute("SELECT value FROM records").fetchall() == [("committed-in-wal",)]
    finally:
        copied.close()
    assert (
        restored / "xducraft_bot/plugins/xducraft_wordcloud/data/avatars/user.png"
    ).read_bytes() == b"avatar"
    assert (
        restored / "xducraft_bot/plugins/xducraft_mc_status/image_cache/server.png"
    ).read_bytes() == b"cache"
    assert (
        restored / "xducraft_bot/shared/data/deployment_overrides.json"
    ).read_bytes() == business_json


def test_closed_wal_database_never_gets_source_sidecars(tmp_path, monkeypatch):
    monkeypatch.delenv("XDUCRAFT_CONFIG_DB", raising=False)
    legacy = tmp_path / "closed-wal-legacy"
    config_db = legacy / "xducraft_bot/shared/data/configuration.sqlite3"
    connection = _open_wal_database(config_db, "closed-wal")
    connection.close()
    source_directory = config_db.parent
    before = {
        path.name: path.read_bytes()
        for path in source_directory.iterdir()
        if path.is_file()
    }
    assert before == {"configuration.sqlite3": config_db.read_bytes()}

    snapshot = tmp_path / "closed-wal-snapshot"
    assert migrate(legacy, snapshot, config_db=config_db) == "migrated"
    after = {
        path.name: path.read_bytes()
        for path in source_directory.iterdir()
        if path.is_file()
    }
    assert after == before
    copied = sqlite3.connect(str(snapshot / "core/configuration.sqlite3"))
    try:
        assert copied.execute("SELECT value FROM records").fetchall() == [("closed-wal",)]
    finally:
        copied.close()

def test_external_config_replaces_default_database_and_its_sidecars(tmp_path, monkeypatch):
    monkeypatch.delenv("XDUCRAFT_CONFIG_DB", raising=False)
    legacy = tmp_path / "legacy"
    default_db = legacy / "xducraft_bot/shared/data/configuration.sqlite3"
    external_db = tmp_path / "external/configuration.sqlite3"
    default_connection = _open_wal_database(default_db, "default")
    external_connection = _open_wal_database(external_db, "external")
    snapshot = tmp_path / "snapshot-external"
    try:
        assert Path(str(default_db) + "-wal").is_file()
        assert Path(str(external_db) + "-wal").is_file()
        assert migrate(legacy, snapshot, config_db=external_db) == "migrated"
        copied = sqlite3.connect(str(snapshot / "core/configuration.sqlite3"))
        try:
            assert copied.execute("SELECT value FROM records").fetchall() == [("external",)]
        finally:
            copied.close()
    finally:
        external_connection.close()
        default_connection.close()

def test_runtime_source_generates_a_fresh_manifest_after_new_writes(tmp_path, monkeypatch):
    monkeypatch.delenv("XDUCRAFT_CONFIG_DB", raising=False)
    legacy = tmp_path / "legacy"
    config_db = legacy / "xducraft_bot/shared/data/configuration.sqlite3"
    connection = _open_wal_database(config_db)
    try:
        first = tmp_path / "first"
        assert migrate(legacy, first, config_db=config_db) == "migrated"
    finally:
        connection.close()
    first_manifest = (first / MANIFEST_NAME).read_bytes()
    _write(first, "plugins/wordcloud/images/new-after-cutover.png", b"new runtime write")
    second = tmp_path / "second"
    assert migrate(first, second, source_layout="runtime") == "migrated"
    assert (second / "plugins/wordcloud/images/new-after-cutover.png").read_bytes() == b"new runtime write"
    assert (second / MANIFEST_NAME).read_bytes() != first_manifest
    manifest = json.loads((second / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["source_layout"] == "runtime"
    assert [item["path"] for item in manifest["files"]].count(MANIFEST_NAME) == 0


def test_rejects_ambiguous_or_unknown_legacy_sources(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    config_db = legacy / "xducraft_bot/shared/data/configuration.sqlite3"
    connection = _open_wal_database(config_db)
    try:
        monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(tmp_path / "unrelated.sqlite3"))
        with pytest.raises(MigrationError, match="--config-db"):
            migrate(legacy, tmp_path / "ambiguous")
        assert not (tmp_path / "ambiguous").exists()

        _write(legacy, "xducraft_bot/plugins/nonebot_plugin_other/data/state.json", b"{}")
        with pytest.raises(MigrationError, match="unknown legacy plugin"):
            migrate(legacy, tmp_path / "unknown", config_db=config_db)
        assert not (tmp_path / "unknown").exists()
    finally:
        connection.close()


def test_dangerous_paths_and_invalid_inputs_never_publish(tmp_path, monkeypatch):
    monkeypatch.delenv("XDUCRAFT_CONFIG_DB", raising=False)
    legacy = tmp_path / "legacy"
    corrupt_db = _write(
        legacy,
        "xducraft_bot/shared/data/configuration.sqlite3",
        b"SQLite format 3\x00" + b"not-a-database",
    )

    nested = legacy / "snapshot"
    with pytest.raises(MigrationError, match="non-nested"):
        migrate(legacy, nested, config_db=corrupt_db)
    assert not nested.exists()

    failed = tmp_path / "failed"
    with pytest.raises(MigrationError, match="SQLite backup"):
        migrate(legacy, failed, config_db=corrupt_db)
    assert not failed.exists()
    assert not list(tmp_path.glob(".failed.tmp-*"))

    malicious = tmp_path / "malicious"
    malicious.mkdir()
    payload = b"escape"
    manifest = {
        "format": MANIFEST_FORMAT,
        "version": MANIFEST_VERSION,
        "layout": "runtime",
        "source_layout": "runtime",
        "directories": [],
        "files": [{
            "path": "../escape",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }],
    }
    (malicious / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    restored = tmp_path / "must-not-exist"
    with pytest.raises(MigrationError, match="unsafe relative path"):
        restore(malicious, restored)
    assert not restored.exists()


def test_rejects_real_symlink_inside_runtime_data(tmp_path, monkeypatch):
    monkeypatch.delenv("XDUCRAFT_CONFIG_DB", raising=False)
    legacy = tmp_path / "legacy-link"
    data = legacy / "xducraft_bot/shared/data"
    data.mkdir(parents=True)
    outside = _write(tmp_path, "outside.bin", b"outside")
    link = data / "linked.bin"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not permit creating a test symlink")

    destination = tmp_path / "linked-snapshot"
    with pytest.raises(MigrationError, match="symbolic link|reparse"):
        migrate(legacy, destination)
    assert not destination.exists()
