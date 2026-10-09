import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ================= Setup Mock =================
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
nonebot.on_command = MagicMock()
nonebot.on_command.return_value.handle.side_effect = pass_through_decorator

sys.path.append(str(Path.cwd()))

import xducraft_bot.plugins.xducraft_pig_bot as pig_module
from xducraft_bot.plugins.xducraft_pig_bot import (
    build_image_url,
    find_images_by_keyword,
    handle_pig_command,
    normalize_switch_action,
    pick_random_image,
)
from xducraft_bot.plugins.xducraft_pig_bot.data_manager import DataManager


@pytest.fixture(autouse=True)
def isolate_pig_storage(tmp_path, monkeypatch):
    global pig_data_manager
    monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(tmp_path / "configuration.sqlite3"))
    pig_data_manager = DataManager(
        legacy_config_path=str(tmp_path / "absent.json"),
        configuration_db_path=str(tmp_path / "configuration.sqlite3"),
    )
    monkeypatch.setattr(pig_module, "pig_data_manager", pig_data_manager)
    for key, getter, setter, lister in (
        ("pig_query", lambda gid: pig_data_manager.get_group_config(gid)["query_enabled"], pig_data_manager.set_query_enabled, None),
        ("pig_auto_push", lambda gid: pig_data_manager.get_group_config(gid)["auto_push_enabled"], pig_data_manager.set_auto_push_enabled, pig_data_manager.list_auto_push_groups),
    ):
        feature = pig_module.feature_gate.get_feature(key)
        monkeypatch.setattr(feature, "getter", getter)
        monkeypatch.setattr(feature, "setter", setter)
        monkeypatch.setattr(feature, "lister", lister)
    yield


@pytest.fixture(autouse=True)
def reset_query_cooldown():
    pig_module._query_cooldown_tracker.clear()
    yield
    pig_module._query_cooldown_tracker.clear()


def build_message_mock(text):
    message = MagicMock()
    message.extract_plain_text.return_value = text
    return message


def build_fake_group_event(group_id=123456, user_id=10001, self_id="10000"):
    class FakeGroupEvent:
        pass

    event = FakeGroupEvent()
    event.group_id = group_id
    event.user_id = user_id
    event.self_id = self_id
    return FakeGroupEvent, event


def test_build_image_url_supports_relative_and_absolute():
    assert build_image_url("/data/a.png") == "https://www.pighub.top/data/a.png"
    assert build_image_url("data/b.png") == "https://www.pighub.top/data/b.png"
    assert build_image_url("https://example.com/a.png") == "https://example.com/a.png"


def test_normalize_switch_action_supports_cn_and_legacy():
    assert normalize_switch_action("on") == "enable"
    assert normalize_switch_action("开启") == "enable"
    assert normalize_switch_action("off") == "disable"
    assert normalize_switch_action("关闭") == "disable"
    assert normalize_switch_action("unknown") == ""


def test_find_images_by_keyword_filters_title_and_filename():
    images = [
        {"id": "1", "title": "坏结局", "filename": "坏结局.png", "url": "u1"},
        {"id": "2", "title": "开心猪", "filename": "happy.jpg", "url": "u2"},
        {"id": "3", "title": "A Pig", "filename": "pig.gif", "url": "u3"},
    ]

    matched_cn = find_images_by_keyword(images, "坏")
    assert len(matched_cn) == 1
    assert matched_cn[0]["id"] == "1"

    matched_en = find_images_by_keyword(images, "pig")
    assert len(matched_en) == 1
    assert matched_en[0]["id"] == "3"

    matched_all = find_images_by_keyword(images, "")
    assert len(matched_all) == 3


def test_find_images_by_keyword_supports_fuzzy_fallback():
    images = [
        {"id": "1", "title": "坏结局", "filename": "坏结局.png", "url": "u1"},
        {"id": "2", "title": "开心猪", "filename": "happy.jpg", "url": "u2"},
    ]

    matched_cn_typo = find_images_by_keyword(images, "坏结剧")
    assert len(matched_cn_typo) >= 1
    assert any(item["id"] == "1" for item in matched_cn_typo)

    matched_en_typo = find_images_by_keyword(images, "hapy")
    assert len(matched_en_typo) >= 1
    assert any(item["id"] == "2" for item in matched_en_typo)


def test_find_images_by_keyword_prefers_exact_before_fuzzy():
    images = [
        {"id": "1", "title": "猪猪开心", "filename": "happy_pig.png", "url": "u1"},
        {"id": "2", "title": "猪猪高兴", "filename": "joyful_pig.png", "url": "u2"},
    ]

    matched = find_images_by_keyword(images, "开心")
    assert len(matched) == 1
    assert matched[0]["id"] == "1"


def test_pick_random_image_empty_returns_none():
    assert pick_random_image([]) is None


def test_data_manager_max_forward_results_default_and_normalize():
    assert pig_data_manager.get_max_forward_results() == 5

    pig_data_manager.set_max_forward_results(8)
    assert pig_data_manager.get_max_forward_results() == 8

    pig_data_manager.set_max_forward_results(0)
    assert pig_data_manager.get_max_forward_results() == 1


def test_group_max_forward_override_inherits_and_preserves_feature_flags():
    pig_data_manager.set_query_enabled(10001, False)
    pig_data_manager.set_auto_push_enabled(10001, True)
    pig_data_manager.set_query_enabled(10002, False)

    assert pig_data_manager.export_group_config(19999) == {"max_forward_results": None}
    assert pig_data_manager.get_max_forward_results(19999) == 5
    assert 19999 not in pig_data_manager.list_configured_groups()

    assert pig_data_manager.update_group_config(10001, {"max_forward_results": 2}) == {
        "max_forward_results": 2
    }
    assert pig_data_manager.get_max_forward_results(10001) == 2
    assert pig_data_manager.get_max_forward_results(10002) == 5
    assert pig_data_manager.get_group_config(10001) == {
        "auto_push_enabled": True,
        "query_enabled": False,
    }
    assert pig_data_manager.get_group_config(10002)["query_enabled"] is False

    pig_data_manager.set_max_forward_results(8)
    assert pig_data_manager.get_max_forward_results(10001) == 2
    assert pig_data_manager.get_max_forward_results(10002) == 8

    assert pig_data_manager.update_group_config(10001, {"max_forward_results": None}) == {
        "max_forward_results": None
    }
    assert pig_data_manager.get_max_forward_results(10001) == 8
    assert pig_data_manager.get_group_config(10001) == {
        "auto_push_enabled": True,
        "query_enabled": False,
    }
    assert pig_data_manager.get_group_config(10002)["query_enabled"] is False


def test_forward_selection_uses_group_specific_limit():
    images = [{"url": f"https://example.com/{index}.png"} for index in range(10)]
    pig_data_manager.set_max_forward_results(5)
    pig_data_manager.update_group_config(10001, {"max_forward_results": 2})

    assert len(pig_module._select_forward_images(images, 10001)) == 2
    assert len(pig_module._select_forward_images(images, 10002)) == 5
    assert len(pig_module._select_forward_images(images)) == 5


def test_legacy_import_is_once_and_manager_instances_share_committed_changes(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"groups": {"123456": {"query_enabled": False}}}), encoding="utf-8")
    database_path = str(tmp_path / "import.sqlite3")
    first = DataManager(legacy_config_path=str(path), configuration_db_path=database_path)
    assert first.get_group_config(123456)["query_enabled"] is False
    first.update_group_config(123456, {"max_forward_results": 2})
    path.write_text("not JSON", encoding="utf-8")
    second = DataManager(legacy_config_path=str(path), configuration_db_path=database_path)
    assert second.get_max_forward_results(123456) == 2
    second.set_auto_push_enabled(123456, True)
    assert first.get_group_config(123456) == {"query_enabled": False, "auto_push_enabled": True}
    assert first.update_group_config(123456, {}) == {"max_forward_results": 2}


@pytest.mark.asyncio
async def test_handle_pig_command_query_disabled(mocker):
    mocker.patch.object(pig_module.pig_command, "finish", AsyncMock())
    fetch = mocker.patch.object(pig_module, "fetch_all_images", AsyncMock())
    mocker.patch.object(pig_module, "is_admin", AsyncMock(return_value=False))
    mocker.patch.object(pig_module, "SUPERUSER", AsyncMock(return_value=False))

    pig_data_manager.set_query_enabled(123456, False)

    _, event = build_fake_group_event(group_id=123456)
    mocker.patch.object(pig_module, "GroupMessageEvent", object)
    bot = MagicMock()

    await handle_pig_command(bot, event, build_message_mock("test"))
    fetch.assert_not_awaited()



@pytest.mark.asyncio
async def test_handle_pig_command_toggle_auto_on(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(pig_module.pig_command, "finish", finish_mock)
    mocker.patch.object(pig_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(pig_module, "SUPERUSER", AsyncMock(return_value=False))

    _, event = build_fake_group_event(group_id=123456)
    mocker.patch.object(pig_module, "GroupMessageEvent", object)
    bot = MagicMock()

    await handle_pig_command(bot, event, build_message_mock("auto on"))

    cfg = pig_data_manager.get_group_config(123456)
    assert cfg["auto_push_enabled"] is True


@pytest.mark.asyncio
async def test_handle_pig_command_query_multi_results_send_forward(mocker):
    send_mock = AsyncMock()
    finish_mock = AsyncMock()
    sample_mock = mocker.patch.object(
        pig_module,
        "random",
        wraps=pig_module.random,
    )
    mocker.patch.object(pig_module.pig_command, "send", send_mock)
    mocker.patch.object(pig_module.pig_command, "finish", finish_mock)
    mocker.patch.object(pig_module, "fetch_all_images", AsyncMock(return_value=[
        {"id": "1", "title": "坏结局 A", "filename": "a.png", "url": "https://example.com/a.png"},
        {"id": "2", "title": "坏结局 B", "filename": "b.png", "url": "https://example.com/b.png"},
        {"id": "3", "title": "坏结局 C", "filename": "c.png", "url": "https://example.com/c.png"},
        {"id": "4", "title": "坏结局 D", "filename": "d.png", "url": "https://example.com/d.png"},
        {"id": "5", "title": "坏结局 E", "filename": "e.png", "url": "https://example.com/e.png"},
        {"id": "6", "title": "坏结局 F", "filename": "f.png", "url": "https://example.com/f.png"},
    ]))

    pig_data_manager.set_query_enabled(123456, True)
    pig_data_manager.set_max_forward_results(5)

    _, event = build_fake_group_event(group_id=123456, self_id="10000")
    mocker.patch.object(pig_module, "GroupMessageEvent", object)

    bot = MagicMock()
    bot.send_group_forward_msg = AsyncMock()

    await handle_pig_command(bot, event, build_message_mock("坏结局"))

    sample_mock.sample.assert_called_once()
    sampled_args = sample_mock.sample.call_args.args
    assert len(sampled_args[0]) == 6
    assert sampled_args[1] == 5
    bot.send_group_forward_msg.assert_awaited_once()
    call_kwargs = bot.send_group_forward_msg.await_args.kwargs
    assert call_kwargs["group_id"] == 123456
    assert len(call_kwargs["messages"]) == 5
    for node in call_kwargs["messages"]:
        content = node["data"]["content"]
        assert str(content).startswith("[CQ:image")
        assert "标题:" not in str(content)
    finish_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_pig_command_private_multi_results_send_private_forward(mocker):
    class FakePrivateEvent:
        pass

    mocker.patch.object(pig_module, "PrivateMessageEvent", FakePrivateEvent)

    send_mock = AsyncMock()
    finish_mock = AsyncMock()
    sample_mock = mocker.patch.object(
        pig_module,
        "random",
        wraps=pig_module.random,
    )
    mocker.patch.object(pig_module.pig_command, "send", send_mock)
    mocker.patch.object(pig_module.pig_command, "finish", finish_mock)
    mocker.patch.object(pig_module, "fetch_all_images", AsyncMock(return_value=[
        {"id": "1", "title": "坏结局 A", "filename": "a.png", "url": "https://example.com/a.png"},
        {"id": "2", "title": "坏结局 B", "filename": "b.png", "url": "https://example.com/b.png"},
        {"id": "3", "title": "坏结局 C", "filename": "c.png", "url": "https://example.com/c.png"},
        {"id": "4", "title": "坏结局 D", "filename": "d.png", "url": "https://example.com/d.png"},
        {"id": "5", "title": "坏结局 E", "filename": "e.png", "url": "https://example.com/e.png"},
        {"id": "6", "title": "坏结局 F", "filename": "f.png", "url": "https://example.com/f.png"},
    ]))

    event = FakePrivateEvent()
    event.user_id = 42
    event.self_id = "10000"

    bot = MagicMock()
    bot.call_api = AsyncMock()

    await handle_pig_command(bot, event, build_message_mock("坏结局"))

    sample_mock.sample.assert_called_once()
    bot.call_api.assert_awaited_once()
    kwargs = bot.call_api.await_args.kwargs
    assert kwargs["user_id"] == 42
    assert kwargs["messages"]
    assert len(kwargs["messages"]) == 5
    finish_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_pig_command_empty_keyword_returns_random_single_image(mocker):
    finish_mock = AsyncMock()
    send_mock = AsyncMock()
    mocker.patch.object(pig_module.pig_command, "finish", finish_mock)
    mocker.patch.object(pig_module.pig_command, "send", send_mock)
    mocker.patch.object(pig_module, "fetch_all_images", AsyncMock(return_value=[
        {"id": "1", "title": "A", "filename": "a.png", "url": "https://example.com/a.png"},
        {"id": "2", "title": "B", "filename": "b.png", "url": "https://example.com/b.png"},
    ]))
    mocker.patch.object(pig_module, "pick_random_image", return_value={
        "id": "2", "title": "B", "filename": "b.png", "url": "https://example.com/b.png"
    })

    _, event = build_fake_group_event(group_id=123456, self_id="10000")
    mocker.patch.object(pig_module, "GroupMessageEvent", object)
    pig_data_manager.set_query_enabled(123456, True)

    bot = MagicMock()
    bot.send_group_forward_msg = AsyncMock()

    await handle_pig_command(bot, event, build_message_mock(""))

    send_mock.assert_not_awaited()
    bot.send_group_forward_msg.assert_not_awaited()
    finish_arg = finish_mock.await_args.args[0]
    assert str(finish_arg).startswith("[CQ:image")


@pytest.mark.asyncio
async def test_handle_pig_command_query_cooldown_blocks_frequent_requests(mocker):
    class FakePrivateEvent:
        pass

    mocker.patch.object(pig_module, "PrivateMessageEvent", FakePrivateEvent)

    finish_mock = AsyncMock()
    mocker.patch.object(pig_module.pig_command, "finish", finish_mock)
    fetch_mock = AsyncMock(return_value=[
        {"id": "1", "title": "单图", "filename": "single.png", "url": "https://example.com/single.png"},
    ])
    mocker.patch.object(pig_module, "fetch_all_images", fetch_mock)

    event = FakePrivateEvent()
    event.user_id = 43
    event.self_id = "10000"

    bot = MagicMock()

    await handle_pig_command(bot, event, build_message_mock("单图"))
    await handle_pig_command(bot, event, build_message_mock("单图"))

    assert fetch_mock.await_count == 1



def test_pig_declaration_validates_and_binds_inherited_revision():
    from xducraft_bot.shared.configuration import ConfigContext, ConfigurationError
    from xducraft_bot.plugins.xducraft_pig_bot.configuration import bind_configuration
    declaration = bind_configuration(pig_data_manager)
    resource = declaration.resources["group"]
    ctx = ConfigContext(10001)
    before = resource.read(ctx)
    resource.write(ctx, {"max_forward_results": 2})
    assert pig_data_manager.get_max_forward_results(10001) == 2
    pig_data_manager.set_max_forward_results(8)
    current = resource.read(ctx)
    assert current.meta["effective"]["max_forward_results"] == 2
    assert current.revision_values != before.revision_values
    with pytest.raises(ConfigurationError):
        resource.write(ctx, {"max_forward_results": 0})
    resource.write(ctx, {"max_forward_results": None})
    assert resource.read(ctx).meta["effective"]["max_forward_results"] == 8


def test_happy_declaration_only_changes_selected_group(tmp_path, monkeypatch):
    from xducraft_bot.shared.config_store import ConfigDocumentStore
    from xducraft_bot.shared.configuration import ConfigContext
    from xducraft_bot.plugins.xducraft_happy_bot import data_manager as happy
    from xducraft_bot.plugins.xducraft_happy_bot.configuration import bind_configuration
    monkeypatch.setattr(happy, "_store", ConfigDocumentStore(
        "happy_bot", happy._default_data, happy._normalize,
        database_path=str(tmp_path / "happy.sqlite3"),
    ))
    happy.set_emoji_id("321")
    happy.set_emoji_id("123", 10001)
    happy.set_emoji_id("456", 10002)
    declaration = bind_configuration(happy)
    assert set(declaration.resources) == {"group"}
    resource = declaration.resources["group"]
    resource.write(ConfigContext(10001), {"emoji_id": "789"})
    assert happy.get_emoji_id(10001) == "789"
    assert happy.get_emoji_id(10002) == "456"
    assert happy.get_emoji_id() == "321"
    resource.write(ConfigContext(10001), {"emoji_id": None})
    assert happy.get_emoji_id(10001) == "321"
    assert happy.get_emoji_id(10002) == "456"


@pytest.mark.asyncio
async def test_scheduled_pig_rechecks_stop_after_fetch(monkeypatch):
    enabled = True
    pig_data_manager.set_auto_push_enabled(10001, True)
    async def prepare():
        nonlocal enabled
        enabled = False
        return [{"url": "https://example.com/pig.png"}]
    monkeypatch.setattr(pig_module.feature_gate, "is_plugin_enabled", lambda *_: enabled)
    monkeypatch.setattr(pig_module, "fetch_all_images", prepare)
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    monkeypatch.setattr(pig_module, "get_bots", lambda: {"1": bot})
    await pig_module.push_random_pig_job()
    bot.send_group_msg.assert_not_awaited()


@pytest.mark.parametrize("legacy", ["not JSON", "[]", "null"])
def test_invalid_legacy_configuration_is_not_silently_replaced(tmp_path, legacy):
    path = tmp_path / "broken.json"
    path.write_text(legacy, encoding="utf-8")
    with pytest.raises(ValueError):
        DataManager(legacy_config_path=str(path), configuration_db_path=str(tmp_path / "broken.sqlite3"))
    path.write_text('{"max_forward_results": 9, "groups": {}}', encoding="utf-8")
    manager = DataManager(legacy_config_path=str(path), configuration_db_path=str(tmp_path / "broken.sqlite3"))
    assert manager.get_max_forward_results() == 9
