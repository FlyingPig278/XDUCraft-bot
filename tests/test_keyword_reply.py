from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from xducraft_bot.plugins import xducraft_keyword as keyword
from xducraft_bot.plugins.xducraft_keyword import data_manager as dm
from xducraft_bot.shared.config_store import ConfigDocumentStore


GROUP_ID = 123456
USER_ID = 654321


class HandlerFinished(Exception):
    pass


class CaptureRejected(Exception):
    pass


class CapturePaused(Exception):
    pass


class FakeMessageEvent:
    def __init__(self, message: Message):
        self._message = message

    def get_message(self) -> Message:
        return self._message


class FakePrivateEvent(FakeMessageEvent):
    def __init__(self, message: Message = Message()):
        super().__init__(message)
        self.user_id = USER_ID


class FakeGroupEvent:
    def __init__(self):
        self.group_id = GROUP_ID
        self.user_id = USER_ID


def _isolated_store(mocker, tmp_path) -> ConfigDocumentStore:
    store = ConfigDocumentStore(
        "keyword", dm._default_config, dm._normalize_config,
        database_path=str(tmp_path / "configuration.sqlite3"),
    )
    mocker.patch.object(dm, "_store", store)
    return store


def test_multi_replies_and_join_replies_persist(mocker, tmp_path):
    _isolated_store(mocker, tmp_path)

    rule = dm.add_rule("规则", ["第一条", "第二条"], group_id=GROUP_ID)
    assert rule is not None
    assert dm.match_rules("触发规则", GROUP_ID)["replies"] == ["第一条", "第二条"]

    assert dm.set_join_replies(GROUP_ID, ["欢迎", "请先看群公告"]) is True
    assert dm.get_join_replies(GROUP_ID) == ["欢迎", "请先看群公告"]


@pytest.mark.asyncio
async def test_private_entry_explains_how_to_find_and_select_group(mocker):
    finish = mocker.patch.object(
        keyword.keyword_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )

    with pytest.raises(HandlerFinished):
        await keyword.handle_command(
            MagicMock(),
            FakePrivateEvent(),
            {},
            Message(),
        )

    help_text = finish.await_args.args[0]
    assert "/关键词 <群号>" in help_text
    assert "目标群发送一次 /关键词" in help_text


@pytest.mark.asyncio
async def test_group_command_only_sends_private_configuration_menu(mocker):
    mocker.patch.object(keyword, "GroupMessageEvent", FakeGroupEvent)
    mocker.patch.object(keyword, "can_manage_group", AsyncMock(return_value=True))
    notify = mocker.patch.object(
        keyword,
        "notify_privately",
        AsyncMock(return_value=True),
    )
    set_enabled = mocker.patch.object(keyword.feature_gate, "set_enabled")
    finish = mocker.patch.object(
        keyword.keyword_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )
    bot = MagicMock()

    with pytest.raises(HandlerFinished):
        await keyword.handle_command(
            bot,
            FakeGroupEvent(),
            {},
            Message("on"),
        )

    set_enabled.assert_not_called()
    notify.assert_awaited_once()
    assert notify.await_args.args[0] is bot
    assert notify.await_args.args[1] == USER_ID
    private_menu = notify.await_args.args[2]
    assert f"/关键词 {GROUP_ID} add 新手教程" in private_menu
    finish.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_private_command_authorizes_target_group_and_enables_it(mocker):
    can_manage = mocker.patch.object(
        keyword,
        "can_manage_group",
        AsyncMock(return_value=True),
    )
    set_enabled = mocker.patch.object(
        keyword.feature_gate,
        "set_enabled",
        return_value=True,
    )
    finish = mocker.patch.object(
        keyword.keyword_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )
    bot = MagicMock()
    event = FakePrivateEvent()

    with pytest.raises(HandlerFinished):
        await keyword.handle_command(
            bot,
            event,
            {},
            Message(f"{GROUP_ID} on"),
        )

    can_manage.assert_awaited_once_with(bot, event, GROUP_ID)
    set_enabled.assert_called_once_with(keyword.FEATURE_KEY, GROUP_ID, True)
    assert f"已开启群 {GROUP_ID}" in finish.await_args.args[0]


@pytest.mark.asyncio
async def test_private_add_without_inline_reply_starts_guided_capture(mocker, tmp_path):
    _isolated_store(mocker, tmp_path)
    mocker.patch.object(keyword, "can_manage_group", AsyncMock(return_value=True))
    pause = mocker.patch.object(
        keyword.keyword_command,
        "pause",
        AsyncMock(side_effect=CapturePaused),
    )
    state = {}

    with pytest.raises(CapturePaused):
        await keyword.handle_command(
            MagicMock(),
            FakePrivateEvent(),
            state,
            Message(f"{GROUP_ID} add 新手教程"),
        )

    capture = state[keyword._CAPTURE_STATE_KEY]
    assert capture["group_id"] == GROUP_ID
    assert capture["keyword"] == "新手教程"
    prompt = pause.await_args.args[0]
    assert f"群 {GROUP_ID}" in prompt
    assert "单独发送“完成”" in prompt


@pytest.mark.asyncio
async def test_keyword_trigger_sends_saved_messages_in_order(mocker):
    mocker.patch.object(keyword.feature_gate, "is_enabled", return_value=True)
    mocker.patch.object(
        keyword.dm,
        "match_rules",
        return_value={"id": "rule", "cooldown": 0, "replies": ["第一条", "第二条"]},
    )
    mocker.patch.object(keyword, "_on_cooldown", return_value=False)

    bot = MagicMock()
    bot.send = AsyncMock()
    event = MagicMock()
    event.group_id = GROUP_ID
    event.message = Message("触发")

    await keyword.handle_keyword(bot, event)

    assert [str(call.args[1]) for call in bot.send.await_args_list] == ["第一条", "第二条"]


@pytest.mark.asyncio
async def test_member_join_mentions_new_member_then_sends_remaining_messages(mocker):
    mocker.patch.object(keyword.feature_gate, "is_enabled", return_value=True)
    mocker.patch.object(keyword.dm, "get_join_replies", return_value=["欢迎加入", "请先看群公告"])

    bot = MagicMock()
    bot.self_id = "10000"
    bot.send = AsyncMock()
    event = MagicMock()
    event.group_id = GROUP_ID
    event.user_id = USER_ID

    await keyword.handle_member_join(bot, event)

    sent = [str(call.args[1]) for call in bot.send.await_args_list]
    assert f"[CQ:at,qq={USER_ID}]" in sent[0]
    assert "欢迎加入" in sent[0]
    assert sent[1] == "请先看群公告"


@pytest.mark.asyncio
async def test_interactive_capture_records_multiple_messages(mocker, tmp_path):
    _isolated_store(mocker, tmp_path)
    state = {
        keyword._CAPTURE_STATE_KEY: {
            "kind": "rule",
            "group_id": GROUP_ID,
            "keyword": "多条",
            "replies": [],
        }
    }
    matcher = MagicMock()
    matcher.reject_receive = AsyncMock(side_effect=CaptureRejected)
    matcher.finish = AsyncMock(side_effect=HandlerFinished)
    finish = mocker.patch.object(
        keyword.keyword_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )

    for text in ("第一条", "第二条"):
        with pytest.raises(CaptureRejected):
            await keyword.receive_configured_reply(
                FakeMessageEvent(Message(text)),
                state,
                matcher,
            )

    with pytest.raises(HandlerFinished):
        await keyword.receive_configured_reply(
            FakeMessageEvent(Message("完成")),
            state,
            matcher,
        )

    assert dm.find_rule("多条", GROUP_ID)["replies"] == ["第一条", "第二条"]
    assert "2 条回复" in finish.await_args.args[0]


def test_message_head_split_preserves_rich_reply_segments():
    message = Message()
    message += MessageSegment.text("add 图片回复 说明文字 ")
    message += MessageSegment.image("https://example.test/image.png")

    head, reply = keyword._split_message_head(message, 2)

    assert head == ["add", "图片回复"]
    assert reply is not None
    assert reply[0].type == "text"
    assert reply[0].data["text"] == "说明文字 "
    assert reply[1].type == "image"
