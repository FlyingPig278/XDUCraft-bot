import json
from pathlib import Path

import pytest


def _prepare_isolated_storage(monkeypatch, tmp_path: Path):
    from xducraft_mc_status import data_manager as dm

    monkeypatch.setattr(
        dm, "_store",
        dm.ConfigDocumentStore(
            "mc_status", dm._default_data, dm._normalize_data,
            database_path=str(tmp_path / "configuration.sqlite3"),
        ),
    )
    return dm


def test_group_query_settings_are_independent_and_clearing_uses_code_defaults(monkeypatch, tmp_path):
    dm = _prepare_isolated_storage(monkeypatch, tmp_path)
    dm.set_group_status_api_source(123456, "custom")
    dm.set_group_status_api_url(123456, "https://group.example.com/status")
    dm.set_group_status_api_source(654321, "jsu")
    assert dm.get_group_status_api_source(123456) == "custom"
    assert dm.get_group_status_api_url(123456) == "https://group.example.com/status"
    assert dm.get_group_status_api_source(654321) == "jsu"
    assert dm.get_group_status_api_url(654321) == ""
    dm.clear_group_status_api_source(123456)
    dm.clear_group_status_api_url(123456)
    assert dm.get_group_status_api_source(123456) == "auto"
    assert dm.get_group_status_api_url(123456) == ""
    assert dm.get_group_status_api_source(654321) == "jsu"


def test_unknown_source_cannot_replace_saved_group_choice(monkeypatch, tmp_path):
    dm = _prepare_isolated_storage(monkeypatch, tmp_path)
    dm.set_group_status_api_source(114514, "jsu")
    assert dm.set_group_status_api_source(114514, "unknown") is False
    assert dm.get_group_status_api_source(114514) == "jsu"


@pytest.mark.parametrize("stored_in_sqlite", [False, True])
def test_legacy_query_settings_freeze_once_and_new_groups_do_not_inherit(
    monkeypatch, tmp_path, stored_in_sqlite,
):
    from xducraft_mc_status import data_manager as dm
    from xducraft_bot.shared.config_store import database

    path = str(tmp_path / "configuration.sqlite3")
    legacy = {
        "__global__": {"status_api_source": "sjtu", "status_api_url": "https://old.example/status"},
        "123456": {"servers": [], "status_api_source": "", "status_api_url": ""},
        "654321": {"servers": [], "status_api_source": "jsu", "status_api_url": ""},
    }
    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(json.dumps(legacy), encoding="utf-8")
    db = database(path)
    if stored_in_sqlite:
        with db.transaction() as connection:
            connection.execute(
                "INSERT INTO config_documents(namespace,value,revision) VALUES('mc_status',?,1)",
                (db.encode(legacy),),
            )
    store = dm.ConfigDocumentStore(
        "mc_status", dm._default_data, dm._normalize_data,
        database_path=path, legacy_path=str(legacy_file),
    )
    monkeypatch.setattr(dm, "_store", store)
    assert dm.get_group_status_api_source(123456) == "sjtu"
    assert dm.get_group_status_api_url(123456) == "https://old.example/status"
    assert dm.get_group_status_api_source(654321) == "jsu"
    legacy_file.write_text("not JSON", encoding="utf-8")
    assert dm.get_group_status_api_source(123456) == "sjtu"
    assert dm.get_group_status_api_source(999999) == "auto"
    assert dm.get_group_status_api_url(999999) == ""
    dm.set_group_status_api_url(123456, "https://changed.example/status")
    assert dm.get_group_status_api_url(654321) == "https://old.example/status"
