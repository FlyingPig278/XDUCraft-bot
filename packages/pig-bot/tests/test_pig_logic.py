import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import xducraft_pig_bot as pig_module
from xducraft_pig_bot import (
    build_image_url,
    find_images_by_keyword,
    handle_pig_command,
    normalize_switch_action,
    pick_random_image,
)
from xducraft_pig_bot.data_manager import DataManager


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


@pytest.fixture
def enabled_pig(enable_plugin, isolate_pig_storage):
    enable_plugin("pig_bot", 123456)


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


def test_data_manager_group_defaults_and_strict_limits():
    assert pig_data_manager.export_group_config(10001) == {"max_forward_results": 5}
    assert pig_data_manager.get_group_config(10001) == {
        "auto_push_enabled": False,
        "query_enabled": False,
    }
    assert 10001 not in pig_data_manager.list_configured_groups()

    pig_data_manager.update_group_config(10001, {"max_forward_results": 8})
    assert pig_data_manager.get_max_forward_results(10001) == 8
    for invalid in (0, None, True, "8"):
        with pytest.raises(ValueError):
            pig_data_manager.update_group_config(10001, {"max_forward_results": invalid})
    with pytest.raises(ValueError):
        pig_data_manager.update_group_config(10001, {})
    assert pig_data_manager.get_max_forward_results(10001) == 8


def test_group_max_forward_limit_is_independent_and_preserves_feature_flags():
    pig_data_manager.set_auto_push_enabled(10001, True)
    pig_data_manager.set_query_enabled(10002, True)

    assert pig_data_manager.export_group_config(19999) == {"max_forward_results": 5}
    assert 19999 not in pig_data_manager.list_configured_groups()

    assert pig_data_manager.update_group_config(10001, {"max_forward_results": 2}) == {
        "max_forward_results": 2
    }
    pig_data_manager.update_group_config(10002, {"max_forward_results": 8})
    assert pig_data_manager.get_max_forward_results(10001) == 2
    assert pig_data_manager.get_max_forward_results(10002) == 8
    assert pig_data_manager.get_max_forward_results(19999) == 5
    assert pig_data_manager.get_group_config(10001) == {
        "auto_push_enabled": True,
        "query_enabled": False,
    }
    assert pig_data_manager.get_group_config(10002) == {
        "auto_push_enabled": False,
        "query_enabled": True,
    }


def test_forward_selection_uses_group_specific_limit():
    images = [{"url": f"https://example.com/{index}.png"} for index in range(10)]
    pig_data_manager.update_group_config(10002, {"max_forward_results": 7})
    pig_data_manager.update_group_config(10001, {"max_forward_results": 2})

    assert len(pig_module._select_forward_images(images, 10001)) == 2
    assert len(pig_module._select_forward_images(images, 10002)) == 7
    assert len(pig_module._select_forward_images(images)) == 5


@pytest.mark.parametrize("legacy_source", ["json", "sqlite"])
def test_legacy_import_is_once_and_manager_instances_share_committed_changes(tmp_path, legacy_source):
    from xducraft_bot.shared.config_store import ConfigDocumentStore
    path = tmp_path / "legacy.json"
    legacy = {
        "max_forward_results": 9,
        "groups": {"123456": {"query_enabled": False}, "234567": {"max_forward_results": 3}},
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")
    database_path = str(tmp_path / "import.sqlite3")
    raw_store = ConfigDocumentStore("pig_bot", lambda: legacy, database_path=database_path)
    if legacy_source == "sqlite":
        raw_store.load()
    first = DataManager(legacy_config_path=str(path), configuration_db_path=database_path)
    assert first.get_group_config(123456)["query_enabled"] is False
    assert first.get_max_forward_results(123456) == 9
    assert first.get_max_forward_results(234567) == 3
    assert first.get_max_forward_results(345678) == 5
    assert first.get_group_config(345678)["query_enabled"] is False
    persisted = raw_store.load()
    assert persisted["schema_version"] == 2
    assert "max_forward_results" not in persisted
    first.update_group_config(123456, {"max_forward_results": 2})
    path.write_text("not JSON", encoding="utf-8")
    second = DataManager(legacy_config_path=str(path), configuration_db_path=database_path)
    assert second.get_max_forward_results(123456) == 2
    second.set_auto_push_enabled(123456, True)
    assert first.get_group_config(123456) == {"query_enabled": False, "auto_push_enabled": True}
    assert first.export_group_config(123456) == {"max_forward_results": 2}
    assert first.get_max_forward_results(234567) == 3


@pytest.mark.asyncio
async def test_handle_pig_command_query_disabled(mocker, enabled_pig):
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
async def test_handle_pig_command_toggle_auto_on(mocker, enabled_pig):
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
async def test_handle_pig_command_query_multi_results_send_forward(mocker, enabled_pig):
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
    pig_data_manager.update_group_config(123456, {"max_forward_results": 5})

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
async def test_handle_pig_command_private_multi_results_send_private_forward(mocker, enabled_pig):
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
async def test_handle_pig_command_empty_keyword_returns_random_single_image(mocker, enabled_pig):
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
async def test_handle_pig_command_query_cooldown_blocks_frequent_requests(mocker, enabled_pig):
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



def test_pig_declaration_validates_independent_group_revisions():
    from xducraft_bot.shared.configuration import ConfigContext, ConfigurationError
    from xducraft_pig_bot.configuration import bind_configuration
    declaration = bind_configuration(pig_data_manager)
    assert set(declaration.resources) == {"group"}
    resource = declaration.resources["group"]
    ctx = ConfigContext(10001)
    before = resource.read(ctx)
    resource.write(ctx, {"max_forward_results": 2})
    current = resource.read(ctx)
    assert current.values == {"max_forward_results": 2}
    assert current.revision_values != before.revision_values
    resource.write(ConfigContext(10002), {"max_forward_results": 8})
    assert resource.read(ctx).revision_values == current.revision_values
    assert resource.read(ConfigContext(10003)).values == {"max_forward_results": 5}
    for invalid in (0, None, True, "8"):
        with pytest.raises(ConfigurationError):
            resource.write(ctx, {"max_forward_results": invalid})
    assert resource.read(ctx).revision_values == current.revision_values

@pytest.mark.asyncio
async def test_scheduled_pig_rechecks_stop_after_fetch(monkeypatch, enable_plugin):
    from xducraft_bot.shared.configuration import set_plugin_enabled
    enable_plugin("pig_bot", 10001)
    pig_data_manager.set_auto_push_enabled(10001, True)

    async def prepare():
        set_plugin_enabled("pig_bot", False, actor="test")
        return [{"url": "https://example.com/pig.png"}]

    fetch = AsyncMock(side_effect=prepare)
    monkeypatch.setattr(pig_module, "fetch_all_images", fetch)
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    monkeypatch.setattr(pig_module, "get_bots", lambda: {"1": bot})
    await pig_module.push_random_pig_job()
    fetch.assert_awaited_once()
    bot.send_group_msg.assert_not_awaited()


@pytest.mark.parametrize("legacy", ["not JSON", "[]", "null"])
def test_invalid_legacy_configuration_is_not_silently_replaced(tmp_path, legacy):
    path = tmp_path / "broken.json"
    path.write_text(legacy, encoding="utf-8")
    with pytest.raises(ValueError):
        DataManager(legacy_config_path=str(path), configuration_db_path=str(tmp_path / "broken.sqlite3"))
    path.write_text('{"max_forward_results": 9, "groups": {"123456": {}}}', encoding="utf-8")
    manager = DataManager(legacy_config_path=str(path), configuration_db_path=str(tmp_path / "broken.sqlite3"))
    assert manager.get_max_forward_results(123456) == 9
    assert manager.get_max_forward_results(234567) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
async def test_pig_total_off_blocks_queries_and_auto_push(mocker, private):
    fetch = mocker.patch.object(pig_module, "fetch_all_images", AsyncMock())
    send = mocker.patch.object(pig_module.pig_command, "send", AsyncMock())
    finish = mocker.patch.object(pig_module.pig_command, "finish", AsyncMock())
    pig_data_manager.set_query_enabled(123456, True)
    pig_data_manager.set_auto_push_enabled(123456, True)
    _, event = build_fake_group_event()
    mocker.patch.object(pig_module, "GroupMessageEvent", type(event))
    if private:
        event = MagicMock(user_id=10001)
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_group_forward_msg = AsyncMock()
    bot.call_api = AsyncMock()
    mocker.patch.object(pig_module, "get_bots", return_value={"1": bot})

    assert not pig_module.feature_gate.is_plugin_enabled("pig_bot")
    await handle_pig_command(bot, event, build_message_mock("test"))
    await pig_module.push_random_pig_job()

    fetch.assert_not_awaited()
    send.assert_not_awaited()
    finish.assert_not_awaited()
    bot.send_group_msg.assert_not_awaited()
    bot.send_group_forward_msg.assert_not_awaited()
    bot.call_api.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_push_enabled_group_does_not_enable_another(mocker, enable_plugin):
    enable_plugin("pig_bot", 10001)
    for group_id in (10001, 10002):
        pig_data_manager.set_auto_push_enabled(group_id, True)
    mocker.patch.object(pig_module, "fetch_all_images", AsyncMock(return_value=[
        {"url": "https://example.com/pig.png"},
    ]))
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    mocker.patch.object(pig_module, "get_bots", return_value={"1": bot})

    await pig_module.push_random_pig_job()

    bot.send_group_msg.assert_awaited_once()
    assert bot.send_group_msg.await_args.kwargs["group_id"] == 10001
    assert not pig_module.feature_gate.is_plugin_enabled("pig_bot", 10002)


@pytest.mark.asyncio
async def test_pig_toggle_requires_group_permission(mocker, enabled_pig):
    finish = mocker.patch.object(pig_module.pig_command, "finish", AsyncMock())
    mocker.patch.object(pig_module, "is_admin", AsyncMock(return_value=False))
    mocker.patch.object(pig_module, "SUPERUSER", AsyncMock(return_value=False))
    event_type, event = build_fake_group_event()
    mocker.patch.object(pig_module, "GroupMessageEvent", event_type)

    await handle_pig_command(MagicMock(), event, build_message_mock("auto on"))

    assert pig_data_manager.get_group_config(event.group_id)["auto_push_enabled"] is False
    finish.assert_awaited_once()
