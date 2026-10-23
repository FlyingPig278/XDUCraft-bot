"""Runtime location boundaries; no installed-code or live-data writes."""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest
import platformdirs
import xducraft_bot

from xducraft_bot.shared import data_paths
from xducraft_bot.shared.config_store import database


@pytest.fixture(autouse=True)
def isolated_namespace(tmp_path, monkeypatch):
    package = tmp_path / "namespace"
    package.mkdir()
    monkeypatch.setattr(xducraft_bot, "__path__", [str(package)])
    monkeypatch.delenv("XDUCRAFT_DATA_DIR", raising=False)
    return package


def test_unique_legacy_namespace_preserves_data_until_explicit_root(
    tmp_path, monkeypatch, isolated_namespace
):
    shared = isolated_namespace / "shared" / "data"
    shared.mkdir(parents=True)
    (shared / "state.json").write_text('{"version": 1}', encoding="utf-8")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "state.json").write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.delenv("XDUCRAFT_DATA_DIR", raising=False)
    assert data_paths.runtime_data_root() is None
    assert data_paths.shared_data_dir() == shared
    assert (data_paths.shared_data_dir() / "state.json").read_text() == '{"version": 1}'
    assert data_paths.plugin_cache_dir("example", legacy) == legacy
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

    assert not (data_paths.shared_data_dir() / "state.json").exists()
    assert (shared / "state.json").read_text() == '{"version": 1}'


def test_new_install_uses_platform_data_without_creating_storage(
    tmp_path, monkeypatch, isolated_namespace
):
    monkeypatch.setattr(
        xducraft_bot,
        "__path__",
        [
            str(isolated_namespace),
            "__editable__.xducraft.finder.__path_hook__",
            str(tmp_path / "missing-editable-hook"),
        ],
    )
    expected = platformdirs.user_data_path("xducraft", appauthor=False)
    locations = [
        expected,
        expected / "core",
        expected / "plugins" / "example",
        expected / "cache" / "example",
    ]
    existed = [path.exists() for path in locations]

    assert data_paths.runtime_data_root() == expected
    assert data_paths.shared_data_dir() == locations[1]
    assert data_paths.plugin_data_dir("example", tmp_path / "legacy") == locations[2]
    assert data_paths.plugin_cache_dir("example", tmp_path / "legacy") == locations[3]
    for package in (isolated_namespace, Path(data_paths.__file__).resolve().parents[1]):
        assert not expected.is_relative_to(package)
    assert [path.exists() for path in locations] == existed
    assert list(isolated_namespace.iterdir()) == []


def test_distinct_legacy_namespaces_fail_closed_until_explicit_root(
    tmp_path, monkeypatch, isolated_namespace
):
    other = tmp_path / "other-namespace"
    for package in (isolated_namespace, other):
        (package / "shared" / "data").mkdir(parents=True)
    monkeypatch.setattr(xducraft_bot, "__path__", [str(isolated_namespace), str(other)])
    legacy = tmp_path / "legacy"
    for resolve in (
        data_paths.runtime_data_root,
        data_paths.shared_data_dir,
        lambda: data_paths.plugin_data_dir("example", legacy),
        lambda: data_paths.plugin_cache_dir("example", legacy),
    ):
        with pytest.raises(data_paths.DataPathError):
            resolve()

    root = tmp_path / "runtime"
    monkeypatch.setenv("XDUCRAFT_DATA_DIR", str(root))
    assert data_paths.runtime_data_root() == root
    assert data_paths.shared_data_dir() == root / "core"
    assert data_paths.plugin_data_dir("example", legacy) == root / "plugins" / "example"
    assert data_paths.plugin_cache_dir("example", legacy) == root / "cache" / "example"
    assert not root.exists()


def test_legacy_namespace_aliases_are_deduplicated(
    monkeypatch, isolated_namespace
):
    shared = isolated_namespace / "shared" / "data"
    shared.mkdir(parents=True)
    alias = isolated_namespace / ".." / isolated_namespace.name
    monkeypatch.setattr(xducraft_bot, "__path__", [str(isolated_namespace), str(alias)])
    assert data_paths.runtime_data_root() is None
    assert data_paths.shared_data_dir() == shared.resolve()


def test_flat_checkout_with_external_config_db_keeps_legacy_paths(
    tmp_path, monkeypatch, isolated_namespace
):
    (isolated_namespace.parent / "pyproject.toml").write_text(
        '[tool.nonebot]\nplugin_dirs = ["xducraft_bot/plugins"]\n', encoding="utf-8"
    )
    legacy = isolated_namespace / "plugins" / "example" / "data"
    legacy.mkdir(parents=True)
    (legacy / "state.json").write_text('{"value": 42}', encoding="utf-8")
    shared = isolated_namespace / "shared" / "data"
    external_db = tmp_path / "external" / "configuration.sqlite3"
    monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(external_db))
    database().set_control("example", None, True)

    assert data_paths.runtime_data_root() is None
    assert data_paths.shared_data_dir() == shared
    assert data_paths.plugin_data_dir("example", legacy) == legacy
    assert (data_paths.plugin_data_dir("example", legacy) / "state.json").read_text() == '{"value": 42}'
    assert data_paths.plugin_cache_dir("example", legacy) == legacy
    assert database().control("example")["enabled"] is True
    assert external_db.is_file()
    assert not shared.exists()


def test_installed_sdk_tree_is_not_mistaken_for_flat_checkout(
    monkeypatch, isolated_namespace
):
    (isolated_namespace.parent / "pyproject.toml").write_text(
        "[tool.nonebot]\n", encoding="utf-8"
    )
    (isolated_namespace / "plugins").mkdir()
    monkeypatch.setattr(data_paths, "_PACKAGE_ROOT", isolated_namespace.resolve())
    expected = platformdirs.user_data_path("xducraft", appauthor=False).resolve()
    assert data_paths.runtime_data_root() == expected
    assert data_paths.shared_data_dir() == expected / "core"
    assert not (isolated_namespace / "shared").exists()


def test_external_plugin_uses_legacy_source_data_without_creating_it(
    tmp_path, monkeypatch, isolated_namespace
):
    (isolated_namespace.parent / "pyproject.toml").write_text(
        '[tool.nonebot]\nplugin_dirs = ["xducraft_bot/plugins"]\n', encoding="utf-8"
    )
    (isolated_namespace / "plugins").mkdir()
    packaged_data = tmp_path / "site-packages" / "xducraft_happy_bot" / "data"
    legacy_relative_path = Path(
        "xducraft_bot/plugins/xducraft_happy_bot/data"
    )
    expected = isolated_namespace.parent / legacy_relative_path

    assert data_paths.runtime_data_root() is None
    assert data_paths.plugin_data_dir(
        "happy_bot", packaged_data, legacy_relative_path=legacy_relative_path,
    ) == expected
    assert data_paths.plugin_cache_dir(
        "happy_bot", packaged_data, legacy_relative_path=legacy_relative_path,
    ) == expected
    assert not expected.exists()
    assert not packaged_data.exists()


@pytest.mark.parametrize("legacy_relative_path", ["../outside", "/absolute/path"])
def test_external_plugin_legacy_path_cannot_escape_source_host(
    tmp_path, monkeypatch, isolated_namespace, legacy_relative_path,
):
    (isolated_namespace.parent / "pyproject.toml").write_text(
        "[tool.nonebot]\n", encoding="utf-8"
    )
    (isolated_namespace / "plugins").mkdir()
    with pytest.raises(data_paths.DataPathError):
        data_paths.plugin_data_dir(
            "example",
            tmp_path / "site-packages" / "example" / "data",
            legacy_relative_path=legacy_relative_path,
        )


@pytest.mark.parametrize("location", ["", "   ", "relative-runtime"])
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


def test_platform_default_cannot_write_into_installed_code(monkeypatch):
    package = Path(data_paths.__file__).resolve().parents[1]
    monkeypatch.setattr(
        data_paths, "user_data_path", lambda *args, **kwargs: package / "runtime"
    )
    with pytest.raises(data_paths.DataPathError):
        data_paths.shared_data_dir()


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
