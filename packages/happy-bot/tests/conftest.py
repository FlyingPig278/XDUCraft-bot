"""Exercise the installed package with disposable configuration and runtime data."""
import gc
import os
import tempfile
from pathlib import Path

import pytest

_mirror = tempfile.TemporaryDirectory(prefix="xducraft-tests-")
_root = Path(_mirror.name)
os.environ["XDUCRAFT_DATA_DIR"] = str(_root / "runtime-data")
os.environ["XDUCRAFT_CONFIG_DB"] = str(_root / "runtime-data" / "core" / "configuration.sqlite3")

import nonebot  # noqa: E402

_cwd = Path.cwd()
try:
    os.chdir(_root)
    nonebot.init(
        _env_file=(str(_root / "nonexistent.test.env"),),
        driver="~none", web_admin_enabled=False, log_level="INFO",
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
def isolated_feature_gate():
    from xducraft_bot.shared import feature_gate
    from xducraft_bot.shared.config_store import ConfigDocumentStore
    registry, store = dict(feature_gate._registry), feature_gate._store
    feature_gate._registry.clear()
    feature_gate._store = ConfigDocumentStore("feature_gate", lambda: {"groups": {}})
    try:
        yield feature_gate
    finally:
        feature_gate._registry.clear()
        feature_gate._registry.update(registry)
        feature_gate._store = store
