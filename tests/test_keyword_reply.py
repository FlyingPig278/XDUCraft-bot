from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment

import xducraft_keyword as keyword
from xducraft_keyword import data_manager as dm
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



def _isolated_store(mocker, tmp_path) -> ConfigDocumentStore:
    store = ConfigDocumentStore(
        "keyword", dm._default_config, dm._normalize_config,
        database_path=str(tmp_path / "configuration.sqlite3"),
    )
    mocker.patch.object(dm, "_store", store)
    return store


@pytest.fixture(autouse=True)
def isolate_keyword_storage(mocker, tmp_path):
    _isolated_store(mocker, tmp_path)
    mocker.patch.object(keyword, "_cooldown", {})


@pytest.fixture
def enabled_keyword(enable_plugin, isolate_keyword_storage):
    enable_plugin("keyword", GROUP_ID)
    keyword.feature_gate.set_enabled(keyword.FEATURE_KEY, GROUP_ID, True)


def test_multi_replies_and_join_replies_persist():

    rule = dm.add_rule("规则", ["第一条", "第二条"], group_id=GROUP_ID)
    assert rule is not None
    assert dm.match_rules("触发规则", GROUP_ID)["replies"] == ["第一条", "第二条"]

    assert dm.set_join_replies(GROUP_ID, ["欢迎", "请先看群公告"]) is True
    assert dm.get_join_replies(GROUP_ID) == ["欢迎", "请先看群公告"]
    assert dm.match_rules("触发规则", GROUP_ID + 1) is None
    assert dm.get_join_replies(GROUP_ID + 1) == []



@pytest.mark.asyncio
async def test_private_command_authorizes_target_group_and_enables_it(mocker, enable_plugin):
    enable_plugin("keyword")
    assert not keyword.feature_gate.is_plugin_enabled("keyword", GROUP_ID)
    can_manage = mocker.patch.object(
        keyword,
        "can_manage_group",
        AsyncMock(return_value=True),
    )
    set_enabled = mocker.spy(keyword.feature_gate, "set_enabled")
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
    assert keyword.feature_gate.is_enabled(keyword.FEATURE_KEY, GROUP_ID)
    assert not keyword.feature_gate.is_plugin_enabled("keyword", GROUP_ID + 1)


@pytest.mark.asyncio
async def test_private_add_without_inline_reply_starts_guided_capture(mocker, enabled_keyword):
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
    assert capture["kind"] == "rule"
    assert capture["replies"] == []
    pause.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("replies", [
    ["第一条", "第二条"],
    ["说明", str(MessageSegment.image("https://example.test/reply.png"))],
])
async def test_keyword_trigger_sends_saved_messages_in_order(mocker, enabled_keyword, replies):
    assert dm.add_rule("触发", replies, group_id=GROUP_ID) is not None

    bot = MagicMock()
    bot.send = AsyncMock()
    event = MagicMock()
    event.group_id = GROUP_ID
    event.message = Message("触发")

    await keyword.handle_keyword(bot, event)

    assert [str(call.args[1]) for call in bot.send.await_args_list] == replies


@pytest.mark.asyncio
async def test_member_join_mentions_new_member_then_sends_remaining_messages(mocker, enabled_keyword):
    dm.set_join_replies(GROUP_ID, ["欢迎加入", "请先看群公告"])

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
async def test_interactive_capture_records_multiple_messages(mocker, enabled_keyword):
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
    assert keyword._CAPTURE_STATE_KEY not in state
    finish.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_private_configuration_denies_non_manager(mocker, enable_plugin):
    enable_plugin("keyword")
    mocker.patch.object(keyword, "can_manage_group", AsyncMock(return_value=False))
    finish = mocker.patch.object(
        keyword.keyword_command, "finish", AsyncMock(side_effect=HandlerFinished),
    )
    state = {}

    with pytest.raises(HandlerFinished):
        await keyword.handle_command(
            MagicMock(), FakePrivateEvent(), state, Message(f"{GROUP_ID} on"),
        )

    finish.assert_awaited_once()
    assert not keyword.feature_gate.is_enabled(keyword.FEATURE_KEY, GROUP_ID)
    assert keyword._CAPTURE_STATE_KEY not in state


@pytest.mark.asyncio
async def test_keyword_total_off_blocks_commands_capture_and_passive_replies(mocker):
    keyword.feature_gate.set_enabled(keyword.FEATURE_KEY, GROUP_ID, True)
    assert dm.add_rule("触发", ["不应发送"], group_id=GROUP_ID) is not None
    dm.set_join_replies(GROUP_ID, ["不应欢迎"])
    finish = mocker.patch.object(keyword.keyword_command, "finish", AsyncMock())
    can_manage = mocker.patch.object(keyword, "can_manage_group", AsyncMock())
    persist = mocker.patch.object(keyword, "persist_reply_media", AsyncMock())
    bot = MagicMock()
    bot.self_id = "10000"
    bot.send = AsyncMock()
    event = MagicMock(group_id=GROUP_ID, user_id=USER_ID)
    event.message = Message("触发")
    capture = {"kind": "rule", "group_id": GROUP_ID, "keyword": "新规则", "replies": []}
    state = {keyword._CAPTURE_STATE_KEY: capture}
    matcher = MagicMock()
    matcher.finish = AsyncMock()
    matcher.reject_receive = AsyncMock()

    assert not keyword.feature_gate.is_plugin_enabled("keyword")
    await keyword.handle_command(
        bot, FakePrivateEvent(), {}, Message(f"{GROUP_ID} on"),
    )
    await keyword.handle_keyword(bot, event)
    await keyword.handle_member_join(bot, event)
    await keyword.receive_configured_reply(
        FakeMessageEvent(Message("不应录制")), state, matcher,
    )

    finish.assert_not_awaited()
    can_manage.assert_not_awaited()
    persist.assert_not_awaited()
    bot.send.assert_not_awaited()
    matcher.finish.assert_not_awaited()
    matcher.reject_receive.assert_not_awaited()
    assert capture["replies"] == []


@pytest.mark.asyncio
async def test_keyword_enabled_group_does_not_activate_another(mocker, enabled_keyword):
    other_group = GROUP_ID + 1
    for group_id in (GROUP_ID, other_group):
        assert dm.add_rule("触发", [str(group_id)], group_id=group_id) is not None
        dm.set_join_replies(group_id, ["欢迎"])
    bot = MagicMock()
    bot.self_id = "10000"
    bot.send = AsyncMock()
    event = MagicMock(user_id=USER_ID)
    event.message = Message("触发")
    event.group_id = other_group

    await keyword.handle_keyword(bot, event)
    await keyword.handle_member_join(bot, event)
    bot.send.assert_not_awaited()

    event.group_id = GROUP_ID
    await keyword.handle_keyword(bot, event)
    bot.send.assert_awaited_once()
    assert str(bot.send.await_args.args[1]) == str(GROUP_ID)
    assert not keyword.feature_gate.is_plugin_enabled("keyword", other_group)


@pytest.mark.asyncio
async def test_keyword_cooldown_is_per_group_and_stops_duplicate_replies(mocker, enabled_keyword, enable_plugin):
    other_group = GROUP_ID + 1
    enable_plugin("keyword", other_group)
    keyword.feature_gate.set_enabled(keyword.FEATURE_KEY, other_group, True)
    assert dm.add_rule("触发", ["回复"], group_id=GROUP_ID, cooldown=60) is not None
    assert dm.add_rule("触发", ["另一群"], group_id=other_group, cooldown=60) is not None
    mocker.patch.object(keyword.time, "monotonic", return_value=100.0)
    bot = MagicMock()
    bot.send = AsyncMock()
    event = MagicMock(group_id=GROUP_ID)
    event.message = Message("触发")

    await keyword.handle_keyword(bot, event)
    await keyword.handle_keyword(bot, event)
    event.group_id = other_group
    await keyword.handle_keyword(bot, event)

    assert [str(call.args[1]) for call in bot.send.await_args_list] == ["回复", "另一群"]


@pytest.mark.asyncio
async def test_keyword_total_stop_between_replies_prevents_remaining_send(mocker, enabled_keyword):
    from xducraft_bot.shared.configuration import set_plugin_enabled
    assert dm.add_rule("触发", ["第一条", "第二条"], group_id=GROUP_ID) is not None

    async def stop_after_send(*args):
        set_plugin_enabled("keyword", False, actor="test")

    bot = MagicMock()
    bot.send = AsyncMock(side_effect=stop_after_send)
    event = MagicMock(group_id=GROUP_ID)
    event.message = Message("触发")

    await keyword.handle_keyword(bot, event)

    bot.send.assert_awaited_once()
    assert str(bot.send.await_args.args[1]) == "第一条"


@pytest.mark.asyncio
async def test_capture_cancel_discards_pending_replies(mocker, enabled_keyword):
    state = {keyword._CAPTURE_STATE_KEY: {
        "kind": "rule", "group_id": GROUP_ID, "keyword": "取消的规则", "replies": ["未保存"],
    }}
    matcher = MagicMock()
    matcher.finish = AsyncMock(side_effect=HandlerFinished)
    matcher.reject_receive = AsyncMock()

    with pytest.raises(HandlerFinished):
        await keyword.receive_configured_reply(FakeMessageEvent(Message("取消")), state, matcher)

    assert keyword._CAPTURE_STATE_KEY not in state
    assert dm.find_rule("取消的规则", GROUP_ID) is None
    matcher.reject_receive.assert_not_awaited()


@pytest.mark.parametrize("legacy_source", ["json", "sqlite"])
def test_legacy_rules_freeze_once_with_stable_ids_and_order(mocker, tmp_path, legacy_source):
    other_group = GROUP_ID + 1
    new_group = GROUP_ID + 2
    opaque_reply = "[CQ:image,file=replyasset://legacy/opaque-image]"
    legacy = {
        "default_cooldown": 42,
        "global_rules": [{
            "id": "shared-id", "keywords": ["同名"], "replies": [opaque_reply, "全局第二条"],
            "match": dm.MATCH_CONTAINS, "enabled": True, "cooldown": 0, "created_at": 11,
        }],
        "groups": {
            str(GROUP_ID): {
                "rules": [{
                    "id": "shared-id", "keywords": ["同名"], "replies": ["本群优先"],
                    "match": dm.MATCH_EXACT, "enabled": True, "cooldown": 0, "created_at": 22,
                }],
                "join_replies": ["已有欢迎"],
            },
            str(other_group): {},
        },
    }
    database_path = str(tmp_path / "legacy-keyword.sqlite3")
    legacy_path = tmp_path / "legacy-keyword.json"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    raw_store = ConfigDocumentStore("keyword", lambda: legacy, database_path=database_path)
    if legacy_source == "sqlite":
        raw_store.load()
    store = ConfigDocumentStore(
        "keyword", dm._default_config, dm._normalize_config,
        legacy_path=str(legacy_path), database_path=database_path,
    )
    mocker.patch.object(dm, "_store", store)

    local_rules = dm.get_group_rules(GROUP_ID)
    assert [rule["replies"] for rule in local_rules] == [
        ["本群优先"], [opaque_reply, "全局第二条"],
    ]
    local_ids = [rule["id"] for rule in local_rules]
    assert local_ids[0] == "shared-id"
    assert len(set(local_ids)) == 2
    assert [rule["created_at"] for rule in local_rules] == [22, 11]
    assert dm.match_rules("同名", GROUP_ID)["replies"] == ["本群优先"]
    assert dm.match_rules("包含同名", GROUP_ID)["replies"] == [opaque_reply, "全局第二条"]
    assert dm.get_group_rules(other_group)[0]["id"] == "shared-id"
    assert dm.get_join_replies(GROUP_ID) == ["已有欢迎"]
    assert dm.get_default_cooldown(other_group) == 42

    persisted = raw_store.load()
    assert persisted["schema_version"] == 2
    assert "global_rules" not in persisted
    assert "default_cooldown" not in persisted
    keyword.feature_gate.set_enabled(keyword.FEATURE_KEY, new_group, False)
    legacy_path.write_text("not JSON", encoding="utf-8")
    reopened = ConfigDocumentStore(
        "keyword", dm._default_config, dm._normalize_config,
        legacy_path=str(legacy_path), database_path=database_path,
    )
    mocker.patch.object(dm, "_store", reopened)
    assert dm.get_group_rules(new_group) == []
    assert dm.get_default_cooldown(new_group) == 10
    assert dm.get_join_replies(new_group) == []
    assert new_group not in map(int, dm.get_config()["groups"])
    assert [rule["id"] for rule in dm.get_group_rules(GROUP_ID)] == local_ids

    payload = dm.export_scope_config(GROUP_ID)
    payload["rules"] = [{
        key: rule[key]
        for key in ("id", "keywords", "match", "enabled", "cooldown", "replies")
    } for rule in payload["rules"]]
    dm.replace_scope_config(GROUP_ID, payload)
    assert dm.get_group_rules(GROUP_ID) == local_rules
    assert dm.get_group_rules(other_group)[0]["replies"] == [opaque_reply, "全局第二条"]
