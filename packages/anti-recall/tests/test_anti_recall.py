"""反撤回的用户可见行为与撤回恢复边界。"""

from pathlib import Path
from typing import Any, Dict, List

import pytest
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GroupRecallNoticeEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.exception import FinishedException

import xducraft_anti_recall as anti_recall
from xducraft_anti_recall.data_manager import AntiRecallStore



@pytest.fixture(autouse=True)
def running_plugin(enable_plugin):
    groups = (2000, 3000, 10001, 10002)
    enable_plugin("anti_recall", *groups)
    for group_id in groups:
        anti_recall.feature_gate.set_enabled("anti_recall", group_id, True)

def _private_event(text: str = "/撤回") -> PrivateMessageEvent:
    message = Message(text)
    return PrivateMessageEvent(
        time=1,
        self_id=9000,
        post_type="message",
        sub_type="friend",
        user_id=1000,
        message_type="private",
        message_id=10,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender={"user_id": 1000, "nickname": "查询者"},
    )


def _group_event(text: str = "/撤回") -> GroupMessageEvent:
    message = Message(text)
    return GroupMessageEvent(
        time=1,
        self_id=9000,
        post_type="message",
        sub_type="normal",
        user_id=1000,
        message_type="group",
        message_id=10,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender={"user_id": 1000, "nickname": "查询者"},
        group_id=2000,
    )


def _recall_event(*, message_id: int = 77) -> GroupRecallNoticeEvent:
    return GroupRecallNoticeEvent(
        time=200,
        self_id=9000,
        post_type="notice",
        notice_type="group_recall",
        user_id=1000,
        group_id=2000,
        operator_id=3000,
        message_id=message_id,
    )


def _temp_store(tmp_path: Path) -> AntiRecallStore:
    return AntiRecallStore(
        db_file=str(tmp_path / "anti_recall.db"),
        legacy_config_path=str(tmp_path / "anti_recall.json"),
        configuration_db_path=str(tmp_path / "configuration.sqlite3"),
        media_dir=str(tmp_path / "media"),
    )


def test_record_node_is_only_original_content_with_native_timestamp():
    record = {
        "sender_name": "树上的珊瑚",
        "user_id": 1000,
        "sent_at": 1_760_000_000,
        "content": [{"type": "text", "text": "你伸手他会直接躲开"}],
    }

    nodes = anti_recall._record_nodes(record, self_id=9000)

    assert len(nodes) == 1
    assert nodes[0]["data"]["name"] == "树上的珊瑚"
    assert nodes[0]["data"]["time"] == 1_760_000_000
    assert nodes[0]["data"]["content"].extract_plain_text() == "你伸手他会直接躲开"


@pytest.mark.asyncio
async def test_group_query_finishes_without_sending_public_hint():
    class Bot:
        async def send(self, *args, **kwargs):
            raise AssertionError("群内 /撤回 不应发送任何消息")

    with pytest.raises(FinishedException):
        await anti_recall.handle_query(Bot(), _group_event(), Message())


@pytest.mark.asyncio
async def test_multiple_groups_render_numbered_private_menu(monkeypatch):
    class Bot:
        def __init__(self):
            self.messages: List[str] = []

        async def get_group_info(self, group_id: int):
            return {"group_name": {2000: "二群", 3000: "三群"}[group_id]}

        async def send_private_msg(self, *, user_id: int, message):
            self.messages.append(str(message))

    event = _private_event()
    bot = Bot()
    anti_recall._pending_group_selections.clear()

    await anti_recall._send_group_menu(
        bot,
        event,
        [
            {"group_id": 2000, "count": 3, "latest": 20},
            {"group_id": 3000, "count": 1, "latest": 10},
        ],
    )

    assert len(bot.messages) == 1
    assert anti_recall._get_pending_selection(event) == [2000, 3000]
    anti_recall._pending_group_selections.clear()


@pytest.mark.asyncio
async def test_admin_recall_recovers_message_when_local_cache_misses(tmp_path, monkeypatch):
    store = _temp_store(tmp_path)
    store.set_config_value("save_media", False)
    monkeypatch.setattr(anti_recall, "store", store)
    monkeypatch.setattr(anti_recall.feature_gate, "is_enabled", lambda *_: True)

    class Bot:
        async def get_msg(self, *, message_id: int):
            assert message_id == 77
            return {
                "message_id": 77,
                "group_id": 2000,
                "time": 123,
                "sender": {"user_id": 1000, "card": "成员"},
                "message": [{"type": "text", "data": {"text": "被管理员撤回"}}],
            }

    await anti_recall.handle_recall(Bot(), _recall_event())

    records = store.list_recalls(group_ids=[2000], limit=10)
    assert len(records) == 1
    assert records[0]["user_id"] == 1000
    assert records[0]["operator_id"] == 3000
    assert records[0]["sent_at"] == 123
    assert records[0]["content"] == [{"type": "text", "text": "被管理员撤回"}]


def test_admin_recall_matches_signed_and_unsigned_message_ids(tmp_path):
    store = _temp_store(tmp_path)
    store.cache_message(
        group_id=2000,
        message_id=-1,
        user_id=1000,
        sender_name="成员",
        sent_at=123,
        content=[{"type": "text", "text": "消息"}],
    )

    cached = store.find_cached_message(2000, 0xFFFFFFFF, user_id=1000)

    assert cached is not None
    assert cached["message_id"] == -1
    assert cached["content"] == [{"type": "text", "text": "消息"}]


@pytest.mark.asyncio
async def test_failed_record_does_not_downgrade_sibling_image_to_text():
    class Bot:
        def __init__(self):
            self.successful_forwards: List[List[Dict[str, Any]]] = []
            self.direct_messages: List[Message] = []

        @staticmethod
        def _has_bad_image(nodes) -> bool:
            for node in nodes:
                content = Message((node.get("data") or {}).get("content") or "")
                for segment in content:
                    if segment.type == "image" and segment.data.get("file") == "bad://image":
                        return True
            return False

        async def call_api(self, api: str, **payload):
            assert api == "send_private_forward_msg"
            if self._has_bad_image(payload["messages"]):
                raise RuntimeError("坏图片")
            self.successful_forwards.append(payload["messages"])

        async def send_private_msg(self, *, user_id: int, message):
            parsed = message if isinstance(message, Message) else Message(message)
            if self._has_bad_image([{"data": {"content": parsed}}]):
                raise RuntimeError("坏图片")
            self.direct_messages.append(parsed)

    good = anti_recall.make_node(
        Message(MessageSegment("image", {"file": "good://image"})),
        "甲",
        1,
        timestamp=100,
    )
    bad = anti_recall.make_node(
        Message(MessageSegment("image", {"file": "bad://image"})),
        "乙",
        2,
        timestamp=101,
    )
    bot = Bot()

    delivered = await anti_recall._send_records_resilient(
        bot,
        user_id=1000,
        bundles=[[good], [bad]],
        source="测试群的撤回记录",
    )

    assert delivered is True
    successful_segments = [
        segment
        for nodes in bot.successful_forwards
        for node in nodes
        for segment in Message(node["data"]["content"])
    ]
    assert any(
        segment.type == "image" and segment.data.get("file") == "good://image"
        for segment in successful_segments
    )
    assert len(bot.direct_messages) == 1
    assert all(segment.type == "text" for segment in bot.direct_messages[0])


def test_retained_records_obey_independent_caps_and_reject_incomplete_replacement(tmp_path):
    store = _temp_store(tmp_path)
    for group_id in (10001, 10002):
        store.update_group_config(group_id, {"max_query_results": 5})
    for group_id in (10001, 10002):
        for message_id in range(12):
            assert store.record_recall(
                group_id, message_id, 90001, "成员", 90002, 100,
                [{"type": "text", "text": str(message_id)}],
            )
    assert store.list_recent_recall_group_stats()[0]["count"] == 12
    store.update_group_config(10001, {"max_query_results": 2})
    assert len(store.list_recalls([10001], limit=100)) == 2
    assert len(store.list_recalls([10002], limit=100)) == 5
    with pytest.raises(ValueError):
        store.update_group_config(10001, {})
    assert len(store.list_recalls([10001], limit=100)) == 2
    with pytest.raises(ValueError):
        store.update_group_config(10001, {"max_query_results": None})
    store.update_group_config(10001, {"max_query_results": 30})
    assert len(store.list_recalls([10001], limit=100)) == 12
    assert len(store.list_recalls([10002], limit=100)) == 5
    assert len(store.list_recalls([10001], limit=1)) == 1
    assert all(item["count"] == 12 for item in store.list_recent_recall_group_stats())


def test_anti_recall_declaration_global_policy_and_group_limit(tmp_path):
    from xducraft_bot.shared.configuration import ConfigContext, ConfigurationError
    from xducraft_anti_recall.configuration import bind_configuration
    store = _temp_store(tmp_path)
    declaration = bind_configuration(store)
    root = declaration.resources["global"]
    group = declaration.resources["group"]
    values = root.read(ConfigContext()).values
    before_other_group = group.read(ConfigContext(10002)).values
    values.update(exempt_user_ids=["090001", "90001"], save_media=False)
    root.write(ConfigContext(), values)
    assert store.is_user_exempt(90001)
    assert store.get_config()["exempt_user_ids"] == [90001]
    group.write(ConfigContext(10001), {"max_query_results": 2})
    assert store.get_effective_group_config(10001)["max_query_results"] == 2
    assert group.read(ConfigContext(10002)).values == before_other_group
    with pytest.raises(ConfigurationError):
        group.write(ConfigContext(10001), {"max_query_results": 3, "save_media": True})
    assert store.get_config()["save_media"] is False


@pytest.mark.asyncio
async def test_total_stop_blocks_selected_group_without_deleting_retained_records(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from xducraft_bot.shared.configuration import set_plugin_enabled
    store = _temp_store(tmp_path)
    store.record_recall(10001, 1, 90001, "成员", 90002, 100, [{"type": "text", "text": "保留记录"}])
    monkeypatch.setattr(anti_recall, "store", store)
    class Bot:
        async def get_group_info(self, **kwargs):
            return {"group_name": "测试群"}
        call_api = AsyncMock()
        send_private_msg = AsyncMock()
    bot = Bot()
    await anti_recall._send_group_records(bot, _private_event(), 10001, 30)
    assert bot.call_api.await_count == 1
    bot.call_api.reset_mock()
    set_plugin_enabled("anti_recall", False, 10001)
    await anti_recall._send_group_records(bot, _private_event(), 10001, 30)
    bot.call_api.assert_not_awaited()
    bot.send_private_msg.assert_not_awaited()
    assert len(store.list_recalls([10001], limit=30)) == 1


@pytest.mark.asyncio
async def test_cleanup_respects_global_total_stop(monkeypatch):
    from unittest.mock import MagicMock
    from xducraft_bot.shared.configuration import set_plugin_enabled
    cleanup = MagicMock()
    monkeypatch.setattr(anti_recall.store, "cleanup", cleanup)
    set_plugin_enabled("anti_recall", False)
    await anti_recall.cleanup_job()
    cleanup.assert_not_called()
