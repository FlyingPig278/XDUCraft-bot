import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
import pytest


def pass_through_decorator(*args, **kwargs):
    def decorator(func):
        return func

    return decorator


mock_scheduler_module = MagicMock()
mock_scheduler = MagicMock()
mock_scheduler.scheduled_job.side_effect = pass_through_decorator
mock_scheduler_module.scheduler = mock_scheduler
sys.modules["nonebot_plugin_apscheduler"] = mock_scheduler_module

import nonebot

nonebot.require = MagicMock()
nonebot.get_driver = MagicMock()
nonebot.on_message = MagicMock()
nonebot.on_message.return_value.handle.side_effect = pass_through_decorator
nonebot.on_command = MagicMock()
nonebot.on_command.return_value.handle.side_effect = pass_through_decorator

sys.path.append(str(Path.cwd()))

from xducraft_bot.plugins.xducraft_wordcloud.data_manager import ChatLogDataManager


@pytest.fixture(autouse=True)
def isolate_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(tmp_path / "configuration.sqlite3"))


def test_enabled_groups_normalization(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    db_file = data_dir / "chat_logs.db"

    data_dir.mkdir(parents=True)
    cfg_file.write_text(
        '{"enabled_groups": ["123", 123, "abc", 456], "min_word_length": 2, "max_words": 100}',
        encoding="utf-8",
    )
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(db_file), legacy_config_path=str(cfg_file))

    assert manager.get_enabled_groups() == [123, 456]


def test_add_and_query_messages(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    manager.add_message(10001, "今天天气不错", created_at=1741737600)  # 2025-03-12
    messages = manager.get_messages_for_date(10001, date(2025, 3, 12))
    assert messages == ["今天天气不错"]


def test_cleanup_keep_last_three_days(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    manager.add_message(10001, "d1", created_at=1741564800)  # 2025-03-10
    manager.add_message(10001, "d2", created_at=1741651200)  # 2025-03-11
    manager.add_message(10001, "d3", created_at=1741737600)  # 2025-03-12
    manager.add_message(10001, "d4", created_at=1741824000)  # 2025-03-13

    deleted = manager.cleanup_old_messages(keep_days=3, ref_date=date(2025, 3, 13))

    assert deleted >= 1
    assert manager.get_messages_for_date(10001, date(2025, 3, 10)) == []
    assert manager.get_messages_for_date(10001, date(2025, 3, 11)) == ["d2"]
    assert manager.get_messages_for_date(10001, date(2025, 3, 12)) == ["d3"]
    assert manager.get_messages_for_date(10001, date(2025, 3, 13)) == ["d4"]


def test_get_messages_for_month(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    manager.add_message(10001, "m1", created_at=1741564800)  # 2025-03-10
    manager.add_message(10001, "m2", created_at=1741651200)  # 2025-03-11
    manager.add_message(10001, "m3", created_at=1744416000)  # 2025-04-12

    messages = manager.get_messages_for_month(10001, 2025, 3)
    assert messages == ["m1", "m2"]


def test_get_messages_for_group(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    manager.add_message(10001, "g1", created_at=1741564800)
    manager.add_message(10001, "g2", created_at=1741651200)
    manager.add_message(10002, "other", created_at=1741651200)

    assert manager.get_messages_for_group(10001) == ["g1", "g2"]


def test_set_group_enabled_switch(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    assert manager.set_group_enabled(10001, True) is True
    assert manager.set_group_enabled(10001, True) is False
    assert manager.is_group_enabled(10001) is True

    assert manager.set_group_enabled(10001, False) is True
    assert manager.set_group_enabled(10001, False) is False
    assert manager.is_group_enabled(10001) is False


def test_get_stopwords_from_stopwordsiso_and_independent_group_words(tmp_path, monkeypatch):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text(
        '{"enabled_groups": [10001], "additional_stopwords": ["自定义词"]}',
        encoding="utf-8",
    )

    fake_module = MagicMock()
    fake_module.stopwords.side_effect = lambda lang: {"zh": {"的"}, "en": {"the"}}.get(lang, set())
    monkeypatch.setitem(sys.modules, "stopwordsiso", fake_module)

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    words = manager.get_stopwords(10001)
    assert "的" in words
    assert "the" in words
    assert "自定义词" in words
    assert "自定义词" not in manager.get_stopwords(10002)


def test_retention_days_config_and_floor(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text('{"retention_days": 15}', encoding="utf-8")

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    assert manager.get_retention_days() == 30


def test_footer_subtitle_config(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text(
        '{"enabled_groups": [10001], "footer_subtitle": "  XDUCraft 群词云  "}',
        encoding="utf-8",
    )

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    assert manager.get_footer_subtitle(10001) == "XDUCraft 群词云"
    assert manager.get_footer_subtitle(10002) == ""


def test_footer_branding_options(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text(
        '{"enabled_groups": [10001], "footer_branding_enabled": false, "footer_branding_text": "  Powered by Test  "}',
        encoding="utf-8",
    )

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    options = manager.get_footer_branding_options(10001)
    assert options["enabled"] is False
    assert options["text"] == "Powered by Test"
    assert manager.get_footer_branding_options(10002)["enabled"] is True


def test_ban_user_ids_normalization_and_switch(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text('{"ban_user_ids": ["10001", 10001, "abc", 10002]}', encoding="utf-8")

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    assert manager.get_ban_user_ids() == [10001, 10002]
    assert manager.is_user_banned(10001) is True
    assert manager.set_user_banned(10003, True) is True
    assert manager.is_user_banned(10003) is True
    assert manager.set_user_banned(10003, False) is True
    assert manager.is_user_banned(10003) is False


def test_legacy_values_freeze_once_and_new_groups_use_code_defaults(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    legacy = {
        "enabled_groups": [10001, 10002],
        "ban_user_ids": [90001],
        "min_word_length": 4,
        "max_words": 240,
        "additional_stopwords": ["legacy"],
        "footer_subtitle": "legacy subtitle",
        "footer_branding_enabled": False,
        "footer_branding_text": "legacy branding",
        "group_overrides": {
            "10003": {
                "min_word_length": None,
                "max_words": None,
                "additional_stopwords": None,
                "footer_subtitle": None,
                "footer_branding_enabled": None,
                "footer_branding_text": None,
            },
            "10004": {
                "max_words": 88,
                "additional_stopwords": [],
                "footer_subtitle": "",
                "footer_branding_enabled": False,
                "footer_branding_text": "",
            },
        },
    }
    cfg_file.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    manager = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(cfg_file),
    )
    frozen = {
        "ban_user_ids": [],
        "min_word_length": 4,
        "max_words": 240,
        "additional_stopwords": ["legacy"],
        "footer_subtitle": "legacy subtitle",
        "footer_branding_enabled": False,
        "footer_branding_text": "legacy branding",
    }
    for group_id in (10001, 10002, 10003):
        assert manager.export_group_config(group_id) == frozen
        assert manager.get_ban_user_ids(group_id) == [90001]
    assert manager.export_group_config(10004) == {
        **frozen, "max_words": 88, "additional_stopwords": [],
        "footer_subtitle": "", "footer_branding_enabled": False, "footer_branding_text": "",
    }

    new_group = manager.export_group_config(10005)
    assert new_group["min_word_length"] == 2
    assert new_group["max_words"] == 200
    assert new_group["additional_stopwords"] == []
    assert new_group["footer_branding_enabled"] is True
    assert new_group["footer_subtitle"] == ""
    assert manager.list_configured_groups() == [10001, 10002, 10003, 10004]
    manager.set_group_enabled(10005, True)
    assert manager.export_group_config(10005) == new_group

    legacy.update(min_word_length=9, max_words=999, additional_stopwords=["changed"])
    cfg_file.write_text(json.dumps(legacy), encoding="utf-8")
    reloaded = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(cfg_file),
    )
    for group_id in (10001, 10002, 10003):
        assert reloaded.export_group_config(group_id) == frozen
    assert reloaded.export_group_config(10005) == new_group


def test_full_group_replacement_is_isolated_and_preserves_empty_values(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(data_dir / "wordcloud_config.json"),
    )
    untouched = manager.export_group_config(10002)
    values = {
        **manager.export_group_config(10001),
        "min_word_length": 5,
        "max_words": 60,
        "additional_stopwords": [],
        "footer_subtitle": "",
        "footer_branding_enabled": False,
        "footer_branding_text": "",
        "ban_user_ids": [90002],
    }
    assert manager.update_group_config(10001, values) == values
    assert manager.get_wordcloud_options(10001) == {"min_word_length": 5, "max_words": 60}
    assert manager.get_footer_subtitle(10001) == ""
    assert manager.get_footer_branding_options(10001) == {"enabled": False, "text": ""}
    assert manager.export_group_config(10002) == untouched

    manager.update_global_config({"ban_user_ids": [90001], "retention_days": 90})
    assert manager.export_group_config(10001) == values
    assert manager.export_group_config(10002) == untouched
    assert manager.get_ban_user_ids(10001) == [90001, 90002]
    assert manager.get_ban_user_ids(10002) == [90001]
    assert manager.get_retention_days() == 90
    reloaded = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(data_dir / "wordcloud_config.json"),
    )
    assert reloaded.export_group_config(10001) == values
    assert reloaded.export_group_config(10002) == untouched


def test_partial_or_null_group_update_rejected_without_losing_saved_values(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(data_dir / "wordcloud_config.json"),
    )
    saved = manager.update_group_config(
        10001, {**manager.export_group_config(10001), "max_words": 88},
    )
    for invalid in ({}, {"max_words": 60}, {**saved, "max_words": None}):
        with pytest.raises(ValueError):
            manager.update_group_config(10001, invalid)
        assert manager.export_group_config(10001) == saved


def test_group_bans_are_additional_to_global_bans(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    assert manager.set_user_banned(90001, True) is True
    assert manager.set_group_user_banned(10001, 90002, True) is True
    assert manager.get_group_ban_user_ids(10001) == [90002]
    assert manager.get_ban_user_ids(10001) == [90001, 90002]
    assert manager.get_ban_user_ids(10002) == [90001]
    assert manager.is_user_banned(90001, 10001) is True
    assert manager.set_group_user_banned(10001, 90001, False) is False
    assert manager.is_user_banned(90001, 10001) is True

    assert manager.set_group_user_banned(10001, 90002, False) is True
    assert manager.export_group_config(10001)["ban_user_ids"] == []
    assert manager.is_user_banned(90002, 10001) is False


def test_delete_message_by_message_id(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    manager.add_message(10001, "foo", created_at=1741737600, message_id=777)
    manager.add_message(10001, "bar", created_at=1741737601, message_id=778)

    deleted = manager.delete_message_by_message_id(10001, 777)
    assert deleted == 1
    assert manager.get_messages_for_date(10001, date(2025, 3, 12)) == ["bar"]


def test_delete_messages_by_user_id(tmp_path):
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(data_dir / "wordcloud_config.json"))

    manager.add_message(10001, "u1-1", created_at=1741737600, user_id=111)
    manager.add_message(10001, "u1-2", created_at=1741737601, user_id=111)
    manager.add_message(10001, "u2", created_at=1741737602, user_id=222)

    deleted = manager.delete_messages_by_user_id(10001, 111)
    assert deleted == 2
    assert manager.get_messages_for_date(10001, date(2025, 3, 12)) == ["u2"]




def test_wordcloud_declaration_round_trip_preserves_concrete_values_and_global_safety(tmp_path):
    from xducraft_bot.shared.configuration import ConfigContext, ConfigurationError
    from xducraft_bot.plugins.xducraft_wordcloud.configuration import bind_configuration
    manager = ChatLogDataManager(
        data_dir=str(tmp_path), db_file=str(tmp_path / "chat.db"),
        legacy_config_path=str(tmp_path / "absent.json"),
        configuration_db_path=str(tmp_path / "settings.sqlite3"),
    )
    manager.set_user_banned(90001, True)
    declaration = bind_configuration(manager)
    resource = declaration.resources["group"]
    ctx = ConfigContext(10001)
    draft = resource.read(ctx).values
    draft.update(ban_user_ids=["090002", "90002"], additional_stopwords=[" ROOT ", "root", ""],
                 footer_subtitle="", footer_branding_text="", footer_branding_enabled=False)
    resource.write(ctx, draft)
    assert manager.get_ban_user_ids(10001) == [90001, 90002]
    assert manager.get_effective_group_config(10001)["additional_stopwords"] == ["root"]
    assert manager.get_footer_subtitle(10001) == ""
    assert manager.get_footer_branding_options(10001) == {"enabled": False, "text": ""}
    manager.set_group_user_banned(10001, 90001, False)
    assert manager.is_user_banned(90001, 10001)
    assert resource.read(ctx).values["ban_user_ids"] == ["90002"]
    assert resource.read(ConfigContext(10002)).values["additional_stopwords"] == []
    draft["ban_user_ids"] = []
    draft["additional_stopwords"] = []
    resource.write(ctx, draft)
    assert manager.get_ban_user_ids(10001) == [90001]
    assert manager.get_effective_group_config(10001)["additional_stopwords"] == []
    with pytest.raises(ConfigurationError):
        resource.write(ctx, {**draft, "retention_days": 30})
    assert manager.get_retention_days() == 1095
    saved = resource.read(ctx).values
    for invalid in (
        {key: None for key in draft},
        {**draft, "max_words": None},
        {**draft, "footer_branding_enabled": "false"},
    ):
        with pytest.raises(ConfigurationError):
            resource.write(ctx, invalid)
        assert resource.read(ctx).values == saved

    global_resource = declaration.resources["global"]
    global_values = global_resource.read(ConfigContext()).values
    global_values.update(ban_user_ids=["090003", "90003"], retention_days=90)
    global_resource.write(ConfigContext(), global_values)
    assert global_resource.read(ConfigContext()).values == {
        "ban_user_ids": ["90003"], "retention_days": 90,
    }
    assert resource.read(ctx).values == saved
    assert manager.get_ban_user_ids(10001) == [90003]
    assert manager.get_retention_days() == 90


def test_sqlite_legacy_migration_does_not_seed_later_known_groups(
    tmp_path, isolated_feature_gate,
):
    from xducraft_bot.shared.config_store import database

    legacy = {
        "enabled_groups": [10001],
        "min_word_length": 5,
        "max_words": 240,
        "additional_stopwords": ["legacy-only"],
        "footer_subtitle": "legacy",
        "footer_branding_enabled": False,
    }
    with database().transaction() as connection:
        connection.execute(
            "INSERT INTO config_documents(namespace, value, revision) VALUES (?, ?, ?)",
            ("wordcloud", json.dumps(legacy), 1),
        )
    data_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(data_dir / "absent.json"),
    )
    assert manager.get_wordcloud_options(10001) == {"min_word_length": 5, "max_words": 240}
    assert manager.get_footer_subtitle(10001) == "legacy"

    isolated_feature_gate.register(
        isolated_feature_gate.Feature(key="migration_probe", name="Migration probe"),
    )
    assert isolated_feature_gate.set_enabled("migration_probe", 10002, True)
    assert 10002 in isolated_feature_gate.list_configured_groups()
    assert manager.get_wordcloud_options(10002) == {"min_word_length": 2, "max_words": 200}
    assert manager.export_group_config(10002)["additional_stopwords"] == []
    assert manager.get_footer_subtitle(10002) == ""
    assert manager.get_footer_branding_options(10002)["enabled"] is True
    assert manager.get_wordcloud_options(10001) == {"min_word_length": 5, "max_words": 240}

    reloaded = ChatLogDataManager(
        data_dir=str(data_dir), db_file=str(data_dir / "chat_logs.db"),
        legacy_config_path=str(data_dir / "absent.json"),
    )
    assert reloaded.export_group_config(10002) == manager.export_group_config(10002)
    assert reloaded.get_wordcloud_options(10001) == {"min_word_length": 5, "max_words": 240}
