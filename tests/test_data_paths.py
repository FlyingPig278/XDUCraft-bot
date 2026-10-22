"""Runtime location boundaries; no installed-code or live-data writes."""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from xducraft_bot.shared import data_paths
from xducraft_bot.shared.config_store import database


def test_root_is_opt_in_and_never_falls_back_to_old_plugin_data(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "state.json").write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.delenv("XDUCRAFT_DATA_DIR", raising=False)
    assert (data_paths.plugin_data_dir("example", legacy) / "state.json").read_text() == '{"version": 1}'

    root = tmp_path / "runtime"
    monkeypatch.setenv("XDUCRAFT_DATA_DIR", str(root))
    selected = data_paths.plugin_data_dir("example", legacy)
    assert not root.exists(), "Resolving a location must not initialize storage"
    assert not (selected / "state.json").exists(), "An explicit fresh root must not import old code-directory data"
    selected.mkdir(parents=True)
    (selected / "state.json").write_text('{"version": 2}', encoding="utf-8")
    assert (legacy / "state.json").read_text() == '{"version": 1}'
    assert not data_paths.plugin_data_dir("other", legacy).exists()
    assert data_paths.plugin_cache_dir("example", legacy) != selected


@pytest.mark.parametrize("location", ["", "relative-runtime"])
def test_invalid_explicit_root_is_not_silently_treated_as_unset(location, monkeypatch):
    monkeypatch.setenv("XDUCRAFT_DATA_DIR", location)
    with pytest.raises(data_paths.DataPathError):
        data_paths.shared_data_dir()


@pytest.mark.parametrize("relation", ["inside", "ancestor"])
def test_runtime_root_cannot_overlap_installed_code(relation, monkeypatch):
    package = Path(data_paths.__file__).resolve().parents[1]
    location = package / "runtime" if relation == "inside" else package.parent
    monkeypatch.setenv("XDUCRAFT_DATA_DIR", str(location))
    with pytest.raises(data_paths.DataPathError):
        data_paths.runtime_data_root()


@pytest.mark.parametrize("plugin_id", ["../outside", "", "nested/plugin"])
def test_owner_key_cannot_escape_its_runtime_directory(plugin_id, tmp_path, monkeypatch):
    monkeypatch.setenv("XDUCRAFT_DATA_DIR", str(tmp_path / "runtime"))
    with pytest.raises(data_paths.DataPathError):
        data_paths.plugin_data_dir(plugin_id, tmp_path / "legacy")


def test_database_override_keeps_its_priority_without_relocating_other_data(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    override = tmp_path / "override.sqlite3"
    explicit = tmp_path / "explicit.sqlite3"
    monkeypatch.setenv("XDUCRAFT_DATA_DIR", str(root))
    monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(override))
    database().set_control("example", None, True)
    database(str(explicit)).set_control("example", None, False)
    with closing(sqlite3.connect(override)) as connection:
        assert connection.execute("SELECT enabled FROM plugin_controls WHERE plugin_id='example'").fetchone()[0] == 1
    with closing(sqlite3.connect(explicit)) as connection:
        assert connection.execute("SELECT enabled FROM plugin_controls WHERE plugin_id='example'").fetchone()[0] == 0
    assert data_paths.plugin_data_dir("example", tmp_path / "legacy").parent == root / "plugins"
    assert not (root / "core").exists()
