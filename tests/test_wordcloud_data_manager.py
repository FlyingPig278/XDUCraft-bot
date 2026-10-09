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


def test_get_stopwords_from_stopwordsiso_and_additional(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text(
        '{"enabled_groups": [], "additional_stopwords": ["自定义词"]}',
        encoding="utf-8",
    )

    fake_module = MagicMock()
    fake_module.stopwords.side_effect = lambda lang: {"zh": {"的"}, "en": {"the"}}.get(lang, set())
    sys.modules["stopwordsiso"] = fake_module

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    words = manager.get_stopwords()
    assert "的" in words
    assert "the" in words
    assert "自定义词" in words


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
    cfg_file.write_text('{"footer_subtitle": "  XDUCraft 群词云  "}', encoding="utf-8")

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    assert manager.get_footer_subtitle() == "XDUCraft 群词云"


def test_footer_branding_options(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    cfg_file.write_text(
        '{"footer_branding_enabled": false, "footer_branding_text": "  Powered by Test  "}',
        encoding="utf-8",
    )

    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    options = manager.get_footer_branding_options()
    assert options["enabled"] is False
    assert options["text"] == "Powered by Test"


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


def test_group_overrides_resolve_without_read_side_effects(tmp_path):
    data_dir = tmp_path / "wordcloud"
    cfg_file = data_dir / "wordcloud_config.json"
    data_dir.mkdir(parents=True)
    initial = {
        "enabled_groups": [10001, 10002],
        "ban_user_ids": [90001],
        "min_word_length": 2,
        "max_words": 200,
        "additional_stopwords": ["root"],
        "footer_subtitle": "root subtitle",
        "footer_branding_enabled": True,
        "footer_branding_text": "root branding",
        "group_overrides": {
            "10003": {"max_words": 88},
        },
    }
    cfg_file.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
    manager = ChatLogDataManager(data_dir=str(data_dir),
    db_file=str(data_dir / "chat_logs.db"), legacy_config_path=str(cfg_file))

    assert manager.export_group_config(10001) == {
        "min_word_length": None,
        "max_words": None,
        "additional_stopwords": None,
        "footer_subtitle": None,
        "footer_branding_enabled": None,
        "footer_branding_text": None,
        "ban_user_ids": None,
    }
    assert manager.get_effective_group_config(10001)["min_word_length"] == 2
    assert manager.list_configured_groups() == [10001, 10002, 10003]
    assert manager.load_config()["group_overrides"] == {"10003": {"max_words": 88}}

    saved = manager.update_group_config(
        10001,
        {
            "min_word_length": 5,
            "max_words": 60,
            "additional_stopwords": [],
            "footer_subtitle": "",
            "footer_branding_enabled": False,
            "footer_branding_text": "",
            "ban_user_ids": [90002],
        },
    )
    assert saved["additional_stopwords"] == []
    assert saved["footer_subtitle"] == ""
    assert saved["footer_branding_text"] == ""
    assert manager.get_effective_group_config(10001) == {
        "min_word_length": 5,
        "max_words": 60,
        "additional_stopwords": [],
        "footer_subtitle": "",
        "footer_branding_enabled": False,
        "footer_branding_text": "",
        "ban_user_ids": [90001, 90002],
    }
    assert manager.get_effective_group_config(10002)["min_word_length"] == 2
    assert manager.get_wordcloud_options(10001) == {
        "min_word_length": 5,
        "max_words": 60,
    }
    assert manager.get_footer_subtitle(10001) == ""
    assert manager.get_footer_branding_options(10001) == {
        "enabled": False,
        "text": "",
    }
    assert manager.get_footer_subtitle(10002) == "root subtitle"

    manager.update_global_config(
        {
            "min_word_length": 3,
            "max_words": 240,
            "additional_stopwords": ["new-root"],
        }
    )
    assert manager.get_effective_group_config(10001)["min_word_length"] == 5
    assert manager.get_effective_group_config(10001)["additional_stopwords"] == []
    assert manager.get_effective_group_config(10002)["min_word_length"] == 3
    assert manager.get_effective_group_config(10002)["additional_stopwords"] == ["new-root"]
    persisted = manager.load_config()
    assert persisted["enabled_groups"] == [10001, 10002]
    assert persisted["group_overrides"]["10003"] == {"max_words": 88}

    reset = manager.update_group_config(
        10001,
        {
            "min_word_length": None,
            "additional_stopwords": None,
            "footer_subtitle": None,
        },
    )
    assert reset["min_word_length"] is None
    assert reset["additional_stopwords"] is None
    assert reset["footer_subtitle"] is None
    assert manager.get_effective_group_config(10001)["min_word_length"] == 3
    assert manager.get_effective_group_config(10001)["additional_stopwords"] == ["new-root"]


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




def test_wordcloud_declaration_preserves_empty_overrides_and_root_bans(tmp_path):
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
    manager.update_group_config(10001, {})
    assert manager.get_group_ban_user_ids(10001) == [90002]
    draft["ban_user_ids"] = []
    draft["additional_stopwords"] = []
    resource.write(ctx, draft)
    assert manager.get_ban_user_ids(10001) == [90001]
    assert manager.get_effective_group_config(10001)["additional_stopwords"] == []
    with pytest.raises(ConfigurationError):
        resource.write(ctx, {**draft, "retention_days": 30})
    assert manager.get_retention_days() == 1095
    resource.write(ctx, {key: None for key in draft})
    assert resource.read(ctx).meta["overridden"] == []
