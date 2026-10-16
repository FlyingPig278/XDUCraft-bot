import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
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
nonebot.on_message = MagicMock()
nonebot.on_message.return_value.handle.side_effect = pass_through_decorator
nonebot.on_command = MagicMock()
nonebot.on_command.return_value.handle.side_effect = pass_through_decorator

sys.path.append(str(Path.cwd()))

import xducraft_bot.plugins.xducraft_wordcloud as wc_module
from xducraft_bot.plugins.xducraft_wordcloud import handle_group_message_record, handle_wordcloud_command
from xducraft_bot.plugins.xducraft_wordcloud.data_manager import ChatLogDataManager

chat_log_data_manager = wc_module.chat_log_data_manager


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path, monkeypatch, isolated_configuration_database):
    global chat_log_data_manager
    monkeypatch.setenv("XDUCRAFT_CONFIG_DB", str(tmp_path / "configuration.sqlite3"))

    temp_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(
        data_dir=str(temp_dir), db_file=str(temp_dir / "chat_logs.db"),
        legacy_config_path=str(temp_dir / "wordcloud_config.json"),
        configuration_db_path=str(tmp_path / "configuration.sqlite3"),
    )
    chat_log_data_manager = manager
    monkeypatch.setattr(wc_module, "chat_log_data_manager", manager)

    feature = wc_module.feature_gate.get_feature(wc_module.FEATURE_KEY)
    assert feature is not None
    monkeypatch.setattr(feature, "getter", manager.is_group_enabled)
    monkeypatch.setattr(feature, "setter", manager.set_group_enabled)
    monkeypatch.setattr(feature, "lister", manager.get_enabled_groups)

    yield

@pytest.fixture
def enabled_wordcloud(isolate_storage, enable_plugin):
    enable_plugin("wordcloud", 123456)



def build_message_mock(text):
    message = MagicMock()
    message.extract_plain_text.return_value = text
    return message


@pytest.mark.asyncio
async def test_wc_on_requires_admin_or_superuser(mocker, enable_plugin):
    enable_plugin("wordcloud")
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=False))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("on"))

    assert not chat_log_data_manager.is_group_enabled(123456)


@pytest.mark.asyncio
async def test_wc_on_and_off_synchronize_saved_group_control(mocker, enable_plugin):
    enable_plugin("wordcloud")
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("on"))
    assert chat_log_data_manager.is_group_enabled(123456) is True
    assert wc_module.feature_gate.is_plugin_enabled("wordcloud", 123456) is True

    await handle_wordcloud_command(bot, event, build_message_mock("off"))
    assert chat_log_data_manager.is_group_enabled(123456) is False
    assert wc_module.feature_gate.is_plugin_enabled("wordcloud", 123456) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("command,expected", [
    ("gen", ["today"]),
    ("gen 2025-03", ["march"]),
    ("gen all", ["march", "today"]),
])
async def test_generation_command_consumes_requested_retained_messages(
    mocker, enabled_wordcloud, command, expected,
):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2025, 4, 12)

    mocker.patch.object(wc_module, "date", FixedDate)
    mocker.patch.object(wc_module.wordcloud_command, "finish", AsyncMock())
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))
    tokenize = mocker.patch.object(wc_module, "_tokenize_messages", side_effect=lambda messages, *_: messages)
    mocker.patch.object(wc_module, "_build_wordcloud_image", return_value="E:/tmp/prepared.png")
    chat_log_data_manager.add_message(123456, "march", user_id=90001, created_at=1741737600)
    chat_log_data_manager.add_message(123456, "today", user_id=90001, created_at=1744416000)
    chat_log_data_manager.add_message(654321, "other-group", user_id=90001, created_at=1744416000)
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    event = MagicMock()
    event.group_id = 123456
    await handle_wordcloud_command(bot, event, build_message_mock(command))
    assert tokenize.call_args.args[0] == expected
    assert bot.send_group_msg.await_args.kwargs["group_id"] == 123456


def test_extract_clean_text_skips_at_and_reply_segments():
    message = [
        SimpleNamespace(type="reply", data={"id": "1"}),
        SimpleNamespace(type="text", data={"text": "你好"}),
        SimpleNamespace(type="at", data={"qq": "10001"}),
        SimpleNamespace(type="text", data={"text": "  世界  "}),
    ]

    assert wc_module._extract_clean_text(message) == "你好 世界"


@pytest.mark.asyncio
async def test_wc_ban_add_by_qq(mocker, enabled_wordcloud):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    args = MagicMock()
    args.extract_plain_text.return_value = "ban add 10086"
    args.__iter__.return_value = iter([])

    await handle_wordcloud_command(bot, event, args)

    assert chat_log_data_manager.is_user_banned(10086, 123456) is True
    assert chat_log_data_manager.is_user_banned(10086) is False


@pytest.mark.asyncio
async def test_wc_ban_add_by_at(mocker, enabled_wordcloud):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    args = MagicMock()
    args.extract_plain_text.return_value = "ban add"
    args.__iter__.return_value = iter([SimpleNamespace(type="at", data={"qq": "10010"})])

    await handle_wordcloud_command(bot, event, args)

    assert chat_log_data_manager.is_user_banned(10010, 123456) is True
    assert chat_log_data_manager.is_user_banned(10010) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("target_kind", ["day", "month", "all"])
async def test_ban_filters_at_generation_not_insert(mocker, enabled_wordcloud, target_kind):
    mocker.patch.object(wc_module, "_build_wordcloud_image", MagicMock(return_value="E:/tmp/fake.png"))
    mocker.patch.object(wc_module, "_tokenize_messages", MagicMock(side_effect=lambda msgs, *_: msgs))

    bot = MagicMock()
    bot.send_group_msg = AsyncMock()

    target_day = date(2025, 3, 12)
    chat_log_data_manager.add_message(123456, "from-banned", user_id=10001, created_at=1741737600)
    chat_log_data_manager.add_message(123456, "from-normal", user_id=10002, created_at=1741737600)
    chat_log_data_manager.set_user_banned(10001, True)

    ok = await wc_module._generate_and_send_for_group(123456, target_kind, target_day, bot)

    assert ok is True
    wc_module._tokenize_messages.assert_called_once()
    token_input_messages = wc_module._tokenize_messages.call_args.args[0]
    assert token_input_messages == ["from-normal"]
    assert chat_log_data_manager.get_messages_for_group(123456) == ["from-banned", "from-normal"]
    chat_log_data_manager.set_user_banned(10001, False)
    assert await wc_module._generate_and_send_for_group(123456, target_kind, target_day, bot)
    assert wc_module._tokenize_messages.call_args.args[0] == ["from-banned", "from-normal"]


@pytest.mark.asyncio
async def test_generation_uses_target_group_configuration_and_global_safety(mocker, enable_plugin):
    enable_plugin("wordcloud", 10001, 10002)
    tokenize_mock = mocker.patch.object(
        wc_module,
        "_tokenize_messages",
        MagicMock(side_effect=lambda messages, _stopwords, _minimum: messages),
    )
    build_mock = mocker.patch.object(
        wc_module,
        "_build_wordcloud_image",
        MagicMock(return_value="E:/tmp/fake.png"),
    )
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    target_day = date(2025, 3, 12)

    chat_log_data_manager.update_global_config(
        {"ban_user_ids": [90001], "retention_days": 90},
    )
    chat_log_data_manager.update_group_config(
        10001,
        {
            **chat_log_data_manager.export_group_config(10001),
            "ban_user_ids": [90002],
            "min_word_length": 6,
            "additional_stopwords": ["group-a-only"],
        },
    )
    chat_log_data_manager.update_group_config(
        10002,
        {
            **chat_log_data_manager.export_group_config(10002),
            "min_word_length": 3,
            "additional_stopwords": ["group-b-only"],
        },
    )
    for group_id in (10001, 10002):
        chat_log_data_manager.add_message(group_id, "global-banned", user_id=90001, created_at=1741737600)
        chat_log_data_manager.add_message(group_id, "locally-banned", user_id=90002, created_at=1741737600)
        chat_log_data_manager.add_message(group_id, "included", user_id=90003, created_at=1741737600)

    assert await wc_module._generate_and_send_for_group(10001, "day", target_day, bot)
    assert await wc_module._generate_and_send_for_group(10002, "day", target_day, bot)

    group_a_call, group_b_call = tokenize_mock.call_args_list
    assert group_a_call.args[0] == ["included"]
    assert group_a_call.args[2] == 6
    assert "group-a-only" in group_a_call.args[1]
    assert "group-b-only" not in group_a_call.args[1]
    assert group_b_call.args[0] == ["locally-banned", "included"]
    assert group_b_call.args[2] == 3
    assert "group-b-only" in group_b_call.args[1]
    assert "group-a-only" not in group_b_call.args[1]
    assert [call.args[0] for call in build_mock.call_args_list] == [10001, 10002]


@pytest.mark.asyncio
async def test_group_local_ban_only_blocks_recording_in_that_group(enable_plugin):
    enable_plugin("wordcloud", 10001, 10002)
    chat_log_data_manager.set_group_enabled(10001, True)
    chat_log_data_manager.set_group_enabled(10002, True)
    chat_log_data_manager.set_group_user_banned(10001, 90002, True)

    for group_id in (10001, 10002):
        event = MagicMock()
        event.group_id = group_id
        event.user_id = 90002
        event.message_id = group_id
        event.message = [SimpleNamespace(type="text", data={"text": "same user"})]
        await handle_group_message_record(event)

    assert chat_log_data_manager.get_messages_for_group(10001) == []
    assert chat_log_data_manager.get_messages_for_group(10002) == ["same user"]


@pytest.mark.asyncio
async def test_banned_user_new_message_not_inserted(enabled_wordcloud):
    group_id = 123456
    user_id = 10001

    chat_log_data_manager.set_group_enabled(group_id, True)
    chat_log_data_manager.set_user_banned(user_id, True)

    event = MagicMock()
    event.group_id = group_id
    event.user_id = user_id
    event.message_id = 999
    event.message = [SimpleNamespace(type="text", data={"text": "这条消息不应入库"})]

    await handle_group_message_record(event)

    assert chat_log_data_manager.get_messages_for_group(group_id) == []


@pytest.mark.asyncio
async def test_wc_clear_user_records(mocker, enabled_wordcloud):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    group_id = 123456
    chat_log_data_manager.add_message(group_id, "u1-a", user_id=10086)
    chat_log_data_manager.add_message(group_id, "u1-b", user_id=10086)
    chat_log_data_manager.add_message(group_id, "u2", user_id=10010)
    chat_log_data_manager.add_message(654321, "other-group", user_id=10086)

    bot = MagicMock()
    event = MagicMock()
    event.group_id = group_id

    args = MagicMock()
    args.extract_plain_text.return_value = "clear 10086"
    args.__iter__.return_value = iter([])

    await handle_wordcloud_command(bot, event, args)

    remain = chat_log_data_manager.get_messages_for_group(group_id)
    assert remain == ["u2"]
    assert chat_log_data_manager.get_messages_for_group(654321) == ["other-group"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_scope", ["global", "group"])
async def test_scheduled_generation_rechecks_real_stop_after_preparation(
    monkeypatch, enable_plugin, stop_scope,
):
    from xducraft_bot.shared.configuration import set_plugin_enabled

    enable_plugin("wordcloud", 10001)
    chat_log_data_manager.set_group_enabled(10001, True)
    chat_log_data_manager.add_message(10001, "可生成词云", user_id=90001, created_at=1741737600)

    async def prepare(function, *args):
        set_plugin_enabled("wordcloud", False, None if stop_scope == "global" else 10001)
        return "E:/tmp/prepared.png"

    monkeypatch.setattr(wc_module.asyncio, "to_thread", prepare)
    monkeypatch.setattr(wc_module, "_tokenize_messages", lambda *_: ["词云"])
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    assert not await wc_module._generate_and_send_for_group(
        10001, "day", date(2025, 3, 12), bot, scheduled=True,
    )
    bot.send_group_msg.assert_not_awaited()
    assert chat_log_data_manager.is_group_enabled(10001) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["default", "global-off", "group-off", "domain-off", "enabled"])
async def test_recording_and_scheduled_generation_require_real_enabled_controls(
    mocker, enable_plugin, state,
):
    from xducraft_bot.shared.configuration import plugin_control, set_plugin_enabled

    group_id = 123456
    if state != "default":
        enable_plugin("wordcloud", group_id)
        chat_log_data_manager.set_group_enabled(group_id, state != "domain-off")
        if state == "global-off":
            set_plugin_enabled("wordcloud", False)
        elif state == "group-off":
            set_plugin_enabled("wordcloud", False, group_id)
    else:
        assert plugin_control("wordcloud")["enabled"] is False
        assert plugin_control("wordcloud", group_id)["enabled"] is False

    build = mocker.patch.object(wc_module, "_build_wordcloud_image", return_value="E:/tmp/prepared.png")
    mocker.patch.object(wc_module, "_tokenize_messages", side_effect=lambda messages, *_: messages)
    chat_log_data_manager.add_message(group_id, "retained", user_id=90001, created_at=1741737600)
    event = SimpleNamespace(
        group_id=group_id, user_id=90002, message_id=777,
        message=[SimpleNamespace(type="text", data={"text": "new message"})],
    )
    await handle_group_message_record(event)
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    generated = await wc_module._generate_and_send_for_group(
        group_id, "day", date(2025, 3, 12), bot, scheduled=True,
    )
    assert generated is (state == "enabled")
    if state == "enabled":
        assert chat_log_data_manager.get_messages_for_group(group_id) == ["retained", "new message"]
        bot.send_group_msg.assert_awaited_once()
    else:
        assert chat_log_data_manager.get_messages_for_group(group_id) == ["retained"]
        build.assert_not_called()
        bot.send_group_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_stop_blocks_qq_mutation_without_changing_saved_group_state(mocker, enable_plugin):
    from xducraft_bot.shared.configuration import plugin_control, set_plugin_enabled

    enable_plugin("wordcloud", 123456)
    chat_log_data_manager.set_group_enabled(123456, True)
    set_plugin_enabled("wordcloud", False)
    mocker.patch.object(wc_module.wordcloud_command, "finish", AsyncMock())
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))
    bot = MagicMock()
    event = SimpleNamespace(group_id=123456)
    await handle_wordcloud_command(bot, event, build_message_mock("off"))
    await handle_wordcloud_command(bot, event, build_message_mock("ban add 10086"))
    assert chat_log_data_manager.is_group_enabled(123456) is True
    assert plugin_control("wordcloud", 123456)["enabled"] is True
    assert chat_log_data_manager.get_group_ban_user_ids(123456) == []


@pytest.mark.asyncio
async def test_qq_ban_updates_round_trip_with_group_configuration(mocker, enabled_wordcloud):
    from xducraft_bot.plugins.xducraft_wordcloud.configuration import bind_configuration
    from xducraft_bot.shared.configuration import ConfigContext

    resource = bind_configuration(chat_log_data_manager).resources["group"]
    context = ConfigContext(123456)
    draft = resource.read(context).values
    draft.update(
        ban_user_ids=["10086"], max_words=88, additional_stopwords=[],
        footer_subtitle="", footer_branding_enabled=False, footer_branding_text="",
    )
    resource.write(context, draft)
    chat_log_data_manager.set_user_banned(10086, True)
    mocker.patch.object(wc_module.wordcloud_command, "finish", AsyncMock())
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))
    await handle_wordcloud_command(
        MagicMock(), SimpleNamespace(group_id=123456), build_message_mock("ban del 10086"),
    )
    assert resource.read(context).values == {**draft, "ban_user_ids": []}
    assert chat_log_data_manager.get_ban_user_ids(123456) == [10086]
    assert chat_log_data_manager.get_group_ban_user_ids(654321) == []

    await handle_wordcloud_command(
        MagicMock(), SimpleNamespace(group_id=123456), build_message_mock("ban add 10010"),
    )
    updated = resource.read(context).values
    assert updated == {**draft, "ban_user_ids": ["10010"]}
    resource.write(context, {**updated, "ban_user_ids": []})
    assert chat_log_data_manager.get_ban_user_ids(123456) == [10086]
    assert chat_log_data_manager.get_wordcloud_options(123456)["max_words"] == 88


@pytest.mark.asyncio
async def test_recall_deletes_only_target_group_message(enable_plugin):
    enable_plugin("wordcloud", 123456)
    chat_log_data_manager.set_group_enabled(123456, True)
    chat_log_data_manager.add_message(123456, "recalled", message_id=777, user_id=10001)
    chat_log_data_manager.add_message(123456, "kept", message_id=778, user_id=10001)
    chat_log_data_manager.add_message(654321, "other-group", message_id=777, user_id=10001)
    await wc_module.handle_group_recall_notice(SimpleNamespace(group_id=123456, message_id=777))
    assert chat_log_data_manager.get_messages_for_group(123456) == ["kept"]
    assert chat_log_data_manager.get_messages_for_group(654321) == ["other-group"]
