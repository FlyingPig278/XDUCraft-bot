from pathlib import Path


def _prepare_isolated_storage(monkeypatch, tmp_path: Path):
    from xducraft_bot.plugins.xducraft_mc_status import data_manager as dm

    isolated_database = tmp_path / "configuration.sqlite3"
    monkeypatch.setattr(
        dm, "_store",
        dm.ConfigDocumentStore(
            "mc_status", lambda: {dm.GLOBAL_CONFIG_KEY: dm._default_global_config()},
            dm._normalize_data, database_path=str(isolated_database),
        ),
    )
    return dm


def test_group_and_global_status_api_url_priority(monkeypatch, tmp_path):
    dm = _prepare_isolated_storage(monkeypatch, tmp_path)

    assert dm.get_global_status_api_url() == ""
    assert dm.get_group_status_api_url(123456) == ""
    assert dm.get_effective_status_api_url(123456) == ("", "none")

    assert dm.set_global_status_api_url("https://global.example.com/status") is True
    assert dm.get_effective_status_api_url(123456) == ("https://global.example.com/status", "global")

    assert dm.set_group_status_api_url(123456, "https://group.example.com/status") is True
    assert dm.get_effective_status_api_url(123456) == ("https://group.example.com/status", "group")

    assert dm.clear_group_status_api_url(123456) is True
    assert dm.get_effective_status_api_url(123456) == ("https://global.example.com/status", "global")

    assert dm.clear_global_status_api_url() is True
    assert dm.get_effective_status_api_url(123456) == ("", "none")


def test_status_api_source_accepts_custom_and_jsu(monkeypatch, tmp_path):
    dm = _prepare_isolated_storage(monkeypatch, tmp_path)

    assert dm.set_status_api_source(114514, "custom") is True
    assert dm.get_status_api_source(114514) == "custom"

    assert dm.set_status_api_source(114514, "jsu") is True
    assert dm.get_status_api_source(114514) == "jsu"

    assert dm.set_status_api_source(114514, "unknown") is False
    assert dm.get_status_api_source(114514) == "jsu"


def test_status_api_source_group_and_global_priority(monkeypatch, tmp_path):
    dm = _prepare_isolated_storage(monkeypatch, tmp_path)

    assert dm.get_effective_status_api_source(123456) == ("auto", "global")

    assert dm.set_global_status_api_source("sjtu") is True
    assert dm.get_effective_status_api_source(123456) == ("sjtu", "global")
    assert dm.get_status_api_source(123456) == "sjtu"

    assert dm.set_group_status_api_source(123456, "jsu") is True
    assert dm.get_effective_status_api_source(123456) == ("jsu", "group")
    assert dm.get_status_api_source(123456) == "jsu"

    assert dm.clear_group_status_api_source(123456) is True
    assert dm.get_effective_status_api_source(123456) == ("sjtu", "global")

    assert dm.clear_global_status_api_source() is True
    assert dm.get_effective_status_api_source(123456) == ("auto", "global")
