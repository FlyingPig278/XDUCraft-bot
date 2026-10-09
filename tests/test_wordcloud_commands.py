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
def isolate_storage(tmp_path, monkeypatch):
    global chat_log_data_manager

    temp_dir = tmp_path / "wordcloud"
    manager = ChatLogDataManager(
        data_dir=str(temp_dir),
        db_file=str(temp_dir / "chat_logs.db"),
        config_file=str(temp_dir / "wordcloud_config.json"),
    )
    chat_log_data_manager = manager
    monkeypatch.setattr(wc_module, "chat_log_data_manager", manager)

    feature = wc_module.feature_gate.get_feature(wc_module.FEATURE_KEY)
    if feature is not None:
        monkeypatch.setattr(feature, "getter", manager.is_group_enabled)
        monkeypatch.setattr(feature, "setter", manager.set_group_enabled)
        monkeypatch.setattr(feature, "lister", manager.get_enabled_groups)

    yield


def build_message_mock(text):
    message = MagicMock()
    message.extract_plain_text.return_value = text
    return message


@pytest.mark.asyncio
async def test_wc_on_requires_admin_or_superuser(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=False))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("on"))

    finish_mock.assert_awaited_once_with("你没有执行该命令的权限")


@pytest.mark.asyncio
async def test_wc_on_and_status(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("on"))
    assert chat_log_data_manager.is_group_enabled(123456) is True

    finish_mock.reset_mock()
    await handle_wordcloud_command(bot, event, build_message_mock("status"))
    finish_mock.assert_awaited_once_with("本群词云状态: 开启")


@pytest.mark.asyncio
async def test_wc_gen_uses_shared_generator(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))
    mocker.patch.object(wc_module, "_generate_and_send_for_group", AsyncMock(return_value=True))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("gen"))

    wc_module._generate_and_send_for_group.assert_awaited_once_with(123456, "day", date.today(), bot)
    finish_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_wc_gen_month_target(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))
    mocker.patch.object(wc_module, "_generate_and_send_for_group", AsyncMock(return_value=True))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("gen 2026-03"))

    wc_module._generate_and_send_for_group.assert_awaited_once_with(123456, "month", date(2026, 3, 1), bot)
    finish_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_wc_gen_all_target(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))
    mocker.patch.object(wc_module, "_generate_and_send_for_group", AsyncMock(return_value=True))

    bot = MagicMock()
    event = MagicMock()
    event.group_id = 123456

    await handle_wordcloud_command(bot, event, build_message_mock("gen all"))

    wc_module._generate_and_send_for_group.assert_awaited_once_with(123456, "all", None, bot)
    finish_mock.assert_awaited_once_with()


def test_extract_clean_text_skips_at_and_reply_segments():
    message = [
        SimpleNamespace(type="reply", data={"id": "1"}),
        SimpleNamespace(type="text", data={"text": "你好"}),
        SimpleNamespace(type="at", data={"qq": "10001"}),
        SimpleNamespace(type="text", data={"text": "  世界  "}),
    ]

    assert wc_module._extract_clean_text(message) == "你好 世界"


@pytest.mark.asyncio
async def test_wc_ban_add_by_qq(mocker):
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

    assert chat_log_data_manager.is_user_banned(10086) is True
    finish_mock.assert_awaited_once_with("已封禁: 10086")


@pytest.mark.asyncio
async def test_wc_ban_add_by_at(mocker):
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

    assert chat_log_data_manager.is_user_banned(10010) is True
    finish_mock.assert_awaited_once_with("已封禁: 10010")


@pytest.mark.asyncio
async def test_ban_filters_at_generation_not_insert(mocker):
    mocker.patch.object(wc_module, "_build_wordcloud_image", MagicMock(return_value="E:/tmp/fake.png"))
    mocker.patch.object(wc_module, "_tokenize_messages", MagicMock(side_effect=lambda msgs, *_: msgs))

    bot = MagicMock()
    bot.send_group_msg = AsyncMock()

    target_day = date.today()
    chat_log_data_manager.add_message(123456, "from-banned", user_id=10001)
    chat_log_data_manager.add_message(123456, "from-normal", user_id=10002)
    chat_log_data_manager.set_user_banned(10001, True)

    ok = await wc_module._generate_and_send_for_group(123456, "day", target_day, bot)

    assert ok is True
    wc_module._tokenize_messages.assert_called_once()
    token_input_messages = wc_module._tokenize_messages.call_args.args[0]
    assert token_input_messages == ["from-normal"]


@pytest.mark.asyncio
async def test_banned_user_new_message_not_inserted():
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
async def test_wc_clear_user_records(mocker):
    finish_mock = AsyncMock()
    mocker.patch.object(wc_module.wordcloud_command, "finish", finish_mock)
    mocker.patch.object(wc_module, "is_admin", AsyncMock(return_value=True))
    mocker.patch.object(wc_module, "SUPERUSER", AsyncMock(return_value=False))

    group_id = 123456
    chat_log_data_manager.add_message(group_id, "u1-a", user_id=10086)
    chat_log_data_manager.add_message(group_id, "u1-b", user_id=10086)
    chat_log_data_manager.add_message(group_id, "u2", user_id=10010)

    bot = MagicMock()
    event = MagicMock()
    event.group_id = group_id

    args = MagicMock()
    args.extract_plain_text.return_value = "clear 10086"
    args.__iter__.return_value = iter([])

    await handle_wordcloud_command(bot, event, args)

    remain = chat_log_data_manager.get_messages_for_group(group_id)
    assert remain == ["u2"]
    finish_mock.assert_awaited_once_with("已清除用户 10086 在本群的 2 条词云记录")
