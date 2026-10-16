"""Collect plugin tests in a disposable source/resource mirror, never live data."""
import gc
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_mirror = tempfile.TemporaryDirectory(prefix="xducraft-tests-")
_root = Path(_mirror.name)
_source = Path(__file__).resolve().parents[1]
shutil.copytree(
    _source / "xducraft_bot", _root / "xducraft_bot",
    ignore=shutil.ignore_patterns("data", "image_cache", "__pycache__"),
)
sys.path.insert(0, str(_root))

import nonebot  # noqa: E402

_cwd = Path.cwd()
try:
    os.chdir(_root)
    nonebot.init(
        _env_file=(str(_root / "nonexistent.test.env"),),
        driver="~fastapi", web_admin_enabled=False, log_level="INFO",
    )
finally:
    os.chdir(_cwd)


def pytest_sessionfinish(session, exitstatus):
    from xducraft_bot.shared.config_store import close_databases
    close_databases()
    gc.collect()
    _mirror.cleanup()


@pytest.fixture(autouse=True)
def isolated_configuration_database(tmp_path, monkeypatch):
    monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(tmp_path / "configuration.sqlite3"))
    yield
    from xducraft_bot.shared.config_store import close_databases
    close_databases()


@pytest.fixture
def enable_plugin(isolated_configuration_database):
    from xducraft_bot.shared.configuration import set_plugin_enabled

    def enable(plugin_id, *group_ids):
        set_plugin_enabled(plugin_id, True, actor="test")
        for group_id in group_ids:
            set_plugin_enabled(plugin_id, True, group_id, actor="test")

    return enable


@pytest.fixture
def isolated_feature_gate(tmp_path):
    from xducraft_bot.shared import feature_gate
    from xducraft_bot.shared.config_store import ConfigDocumentStore
    registry, store = dict(feature_gate._registry), feature_gate._store
    feature_gate._registry.clear()
    feature_gate._store = ConfigDocumentStore(
        "feature_gate", lambda: {"groups": {}},
    )
    try:
        yield feature_gate
    finally:
        feature_gate._registry.clear()
        feature_gate._registry.update(registry)
        feature_gate._store = store
