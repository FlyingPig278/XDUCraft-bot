import pytest
from unittest.mock import MagicMock, AsyncMock

import xducraft_mc_update as mc_update_module
from xducraft_mc_update.data_manager import data_manager
from xducraft_mc_update import (
    check_update,
    format_release_time,
    handle_mc_command,
    normalize_command_action,
)

# --- 构造一个“刁钻”的数据 ---
# 假设最新正式版是 1.21.11，最新快照是 26w10a
# 但是列表里，第0个是快照，第1个才是正式版
FAKE_API_DATA = {
    "latest": {
        "release": "1.21.11",
        "snapshot": "26w10a"
    },
    "versions": [
        {
            "id": "26w10a",  # 快照
            "type": "snapshot",
            "releaseTime": "2026-03-01T10:00:00+00:00"  # 快照时间
        },
        {
            "id": "1.21.11",  # 正式版 (在列表第二个位置)
            "type": "release",
            "releaseTime": "2026-02-28T08:00:00+00:00"  # 正式版时间
        },
        {
            "id": "1.20.0",
            "type": "release",
            "releaseTime": "2024-01-01T00:00:00+00:00"
        }
    ]
}


ROLLBACK_API_DATA = {
    "latest": {
        "release": "1.21.11",
        "snapshot": "26.1-pre-1"
    },
    "versions": [
        {
            "id": "26.1-pre-2",
            "type": "snapshot",
            "releaseTime": "2026-03-13T12:55:35+00:00"
        },
        {
            "id": "26.1-pre-1",
            "type": "snapshot",
            "releaseTime": "2026-03-10T13:00:38+00:00"
        },
        {
            "id": "1.21.11",
            "type": "release",
            "releaseTime": "2026-02-28T08:00:00+00:00"
        }
    ]
}


SNAPSHOT_9_API_DATA = {
    "latest": {
        "release": "1.21.11",
        "snapshot": "26.1-snapshot-9"
    },
    "versions": [
        {
            "id": "26.1-snapshot-9",
            "type": "snapshot",
            "releaseTime": "2026-02-18T10:13:30+00:00"
        },
        {
            "id": "1.21.11",
            "type": "release",
            "releaseTime": "2026-02-27T11:00:00+00:00"
        }
    ]
}


PRE_1_API_DATA = {
    "latest": {
        "release": "1.21.11",
        "snapshot": "26.1-pre-1"
    },
    "versions": [
        {
            "id": "26.1-pre-1",
            "type": "snapshot",
            "releaseTime": "2026-03-10T13:00:38+00:00"
        },
        {
            "id": "26.1-snapshot-11",
            "type": "snapshot",
            "releaseTime": "2026-03-03T13:01:51+00:00"
        },
        {
            "id": "26.1-snapshot-10",
            "type": "snapshot",
            "releaseTime": "2026-02-24T13:03:38+00:00"
        },
        {
            "id": "26.1-snapshot-9",
            "type": "snapshot",
            "releaseTime": "2026-02-18T10:13:30+00:00"
        },
        {
            "id": "1.21.11",
            "type": "release",
            "releaseTime": "2026-02-27T11:00:00+00:00"
        }
    ]
}


PRE_2_API_DATA = {
    "latest": {
        "release": "1.21.11",
        "snapshot": "26.1-pre-2"
    },
    "versions": [
        {
            "id": "26.1-pre-2",
            "type": "snapshot",
            "releaseTime": "2026-03-13T12:55:35+00:00"
        },
        {
            "id": "26.1-pre-1",
            "type": "snapshot",
            "releaseTime": "2026-03-10T13:00:38+00:00"
        },
        {
            "id": "26.1-snapshot-11",
            "type": "snapshot",
            "releaseTime": "2026-03-03T13:01:51+00:00"
        },
        {
            "id": "26.1-snapshot-10",
            "type": "snapshot",
            "releaseTime": "2026-02-24T13:03:38+00:00"
        },
        {
            "id": "26.1-snapshot-9",
            "type": "snapshot",
            "releaseTime": "2026-02-18T10:13:30+00:00"
        },
        {
            "id": "1.21.11",
            "type": "release",
            "releaseTime": "2026-02-27T11:00:00+00:00"
        }
    ]
}


FINAL_RELEASE_API_DATA = {
    "latest": {
        "release": "1.21.12",
        "snapshot": "26.1-pre-2"
    },
    "versions": [
        {
            "id": "1.21.12",
            "type": "release",
            "releaseTime": "2026-03-17T09:00:00+00:00"
        },
        {
            "id": "26.1-pre-2",
            "type": "snapshot",
            "releaseTime": "2026-03-13T12:55:35+00:00"
        },
        {
            "id": "26.1-pre-1",
            "type": "snapshot",
            "releaseTime": "2026-03-10T13:00:38+00:00"
        },
        {
            "id": "1.21.11",
            "type": "release",
            "releaseTime": "2026-02-27T11:00:00+00:00"
        }
    ]
}


@pytest.fixture(autouse=True)
def isolate_mc_update_storage(tmp_path, enable_plugin):
    original_dir = data_manager.data_dir
    original_file = data_manager.data_file

    temp_dir = tmp_path / "mc_update_data"
    temp_file = temp_dir / "subscription.json"

    data_manager.data_dir = str(temp_dir)
    data_manager.data_file = str(temp_file)
    data_manager._ensure_file()
    data_manager.reload()
    enable_plugin("mc_update", 123456)

    yield

    data_manager.data_dir = original_dir
    data_manager.data_file = original_file
    data_manager._ensure_file()
    data_manager.reload()


def write_state(*, groups=None, release_id="", release_time="", snapshot_id="", snapshot_time=""):
    data_manager._save({
        "groups": groups or [],
        "versions": {
            "release": {
                "id": release_id,
                "release_time": release_time,
            },
            "snapshot": {
                "id": snapshot_id,
                "release_time": snapshot_time,
            },
        },
    })


def setup_http_and_bot(mocker, payload):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload

    mock_client = mocker.patch("httpx.AsyncClient")
    mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

    mock_bot = MagicMock()
    mock_bot.send_group_msg = AsyncMock()
    mocker.patch("xducraft_mc_update.get_bots", return_value={"bot1": mock_bot})
    return mock_bot


def setup_http_sequence_and_bot(mocker, payloads):
    mock_responses = []
    for payload in payloads:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = payload
        mock_responses.append(mock_response)

    mock_client = mocker.patch("httpx.AsyncClient")
    mock_client.return_value.__aenter__.return_value.get.side_effect = mock_responses

    mock_bot = MagicMock()
    mock_bot.send_group_msg = AsyncMock()
    mocker.patch("xducraft_mc_update.get_bots", return_value={"bot1": mock_bot})
    return mock_bot


def build_message_mock(text):
    message = MagicMock()
    message.extract_plain_text.return_value = text
    return message


@pytest.mark.asyncio
async def test_mc_update_logic(mocker):
    """测试双版本更新时，时间按各自 releaseTime 匹配并转为 UTC+8。"""

    mock_bot = setup_http_and_bot(mocker, FAKE_API_DATA)

    write_state(
        groups=[123456],
        release_id="1.20.0",
        release_time="2024-01-01T00:00:00+00:00",
        snapshot_id="26w09a",
        snapshot_time="2026-02-20T09:00:00+00:00",
    )

    await check_update()

    mock_bot.send_group_msg.assert_called_once()

    call_args = mock_bot.send_group_msg.call_args
    sent_msg = call_args.kwargs.get("message", "") or call_args.args[1]

    assert "版本号：1.21.11" in sent_msg
    assert "发布时间：2026-02-28 16:00:00 UTC+8" in sent_msg
    assert "版本号：26w10a" in sent_msg
    assert "发布时间：2026-03-01 18:00:00 UTC+8" in sent_msg


@pytest.mark.asyncio
async def test_first_run_safety(mocker):
    """测试首次运行（本地无数据）：只记录，不炸群"""

    mock_bot = setup_http_and_bot(mocker, FAKE_API_DATA)

    write_state(groups=[123456])

    await check_update()

    mock_bot.send_group_msg.assert_not_called()
    assert data_manager.get_last_record("release") == {
        "id": "1.21.11",
        "release_time": "2026-02-28T08:00:00+00:00",
    }
    assert data_manager.get_last_record("snapshot") == {
        "id": "26w10a",
        "release_time": "2026-03-01T10:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_ignore_manifest_latest_rollback(mocker):
    """测试 manifest.latest 回摆时，不会把旧快照重新推送出来。"""

    mock_bot = setup_http_and_bot(mocker, ROLLBACK_API_DATA)

    write_state(
        groups=[123456],
        release_id="1.21.11",
        release_time="2026-02-28T08:00:00+00:00",
        snapshot_id="26.1-pre-2",
        snapshot_time="2026-03-13T12:55:35+00:00",
    )

    await check_update()

    mock_bot.send_group_msg.assert_not_called()
    assert data_manager.get_last_record("snapshot") == {
        "id": "26.1-pre-2",
        "release_time": "2026-03-13T12:55:35+00:00",
    }


@pytest.mark.asyncio
async def test_snapshot_to_prerelease_to_release_sequence(mocker):
    """测试 26.1-snapshot-9 -> pre-1 -> pre-2 -> release 的完整演进链路。"""

    mock_bot = setup_http_sequence_and_bot(
        mocker,
        [
            SNAPSHOT_9_API_DATA,
            PRE_1_API_DATA,
            PRE_2_API_DATA,
            FINAL_RELEASE_API_DATA,
        ],
    )

    write_state(groups=[123456])

    await check_update()
    mock_bot.send_group_msg.assert_not_called()
    assert data_manager.get_last_record("release") == {
        "id": "1.21.11",
        "release_time": "2026-02-27T11:00:00+00:00",
    }
    assert data_manager.get_last_record("snapshot") == {
        "id": "26.1-snapshot-9",
        "release_time": "2026-02-18T10:13:30+00:00",
    }

    await check_update()
    assert mock_bot.send_group_msg.await_count == 1
    pre_1_msg = mock_bot.send_group_msg.await_args_list[0].kwargs.get("message", "")
    assert "🧪 Minecraft 快照版更新！" in pre_1_msg
    assert "版本号：26.1-pre-1" in pre_1_msg
    assert "发布时间：2026-03-10 21:00:38 UTC+8" in pre_1_msg
    assert data_manager.get_last_record("snapshot") == {
        "id": "26.1-pre-1",
        "release_time": "2026-03-10T13:00:38+00:00",
    }

    await check_update()
    assert mock_bot.send_group_msg.await_count == 2
    pre_2_msg = mock_bot.send_group_msg.await_args_list[1].kwargs.get("message", "")
    assert "🧪 Minecraft 快照版更新！" in pre_2_msg
    assert "版本号：26.1-pre-2" in pre_2_msg
    assert "发布时间：2026-03-13 20:55:35 UTC+8" in pre_2_msg
    assert data_manager.get_last_record("snapshot") == {
        "id": "26.1-pre-2",
        "release_time": "2026-03-13T12:55:35+00:00",
    }

    await check_update()
    assert mock_bot.send_group_msg.await_count == 3
    release_msg = mock_bot.send_group_msg.await_args_list[2].kwargs.get("message", "")
    assert "🎉 Minecraft 正式版更新！" in release_msg
    assert "版本号：1.21.12" in release_msg
    assert "发布时间：2026-03-17 17:00:00 UTC+8" in release_msg
    assert "26.1-pre-2" not in release_msg
    assert data_manager.get_last_record("release") == {
        "id": "1.21.12",
        "release_time": "2026-03-17T09:00:00+00:00",
    }
    assert data_manager.get_last_record("snapshot") == {
        "id": "26.1-pre-2",
        "release_time": "2026-03-13T12:55:35+00:00",
    }


def test_data_manager_rejects_older_snapshot_record():
    write_state(
        snapshot_id="26.1-pre-2",
        snapshot_time="2026-03-13T12:55:35+00:00",
    )

    updated = data_manager.update_version(
        "snapshot",
        "26.1-pre-1",
        "2026-03-10T13:00:38+00:00",
    )

    assert updated is False
    assert data_manager.get_last_record("snapshot") == {
        "id": "26.1-pre-2",
        "release_time": "2026-03-13T12:55:35+00:00",
    }


def test_format_release_time_to_utc_plus_8():
    assert format_release_time("2026-03-13T12:55:35+00:00") == "2026-03-13 20:55:35 UTC+8"


def test_normalize_command_action_supports_chinese_and_legacy():
    assert normalize_command_action("订阅") == "enable"
    assert normalize_command_action("开启") == "enable"
    assert normalize_command_action("on") == "enable"
    assert normalize_command_action("取消订阅") == "disable"
    assert normalize_command_action("关闭") == "disable"
    assert normalize_command_action("off") == "disable"
    assert normalize_command_action("未知命令") == ""


@pytest.mark.asyncio
async def test_handle_mc_command_supports_chinese_subscribe(mocker):
    mocker.patch.object(mc_update_module, "SUPERUSER", AsyncMock(return_value=True))
    finish_mock = AsyncMock()
    mocker.patch.object(mc_update_module.mc_command, "finish", finish_mock)

    event = MagicMock()
    event.group_id = 123456
    bot = MagicMock()

    await handle_mc_command(bot, event, build_message_mock("订阅"))

    assert 123456 in data_manager.get_subscribed_groups()


@pytest.mark.asyncio
async def test_handle_mc_command_supports_legacy_disable(mocker):
    mocker.patch.object(mc_update_module, "SUPERUSER", AsyncMock(return_value=True))
    finish_mock = AsyncMock()
    mocker.patch.object(mc_update_module.mc_command, "finish", finish_mock)

    write_state(groups=[123456])

    event = MagicMock()
    event.group_id = 123456
    bot = MagicMock()

    await handle_mc_command(bot, event, build_message_mock("off"))

    assert 123456 not in data_manager.get_subscribed_groups()


@pytest.mark.asyncio
async def test_handle_mc_command_shows_chinese_usage_for_unknown_action(mocker):
    mocker.patch.object(mc_update_module, "SUPERUSER", AsyncMock(return_value=True))
    finish_mock = AsyncMock()
    mocker.patch.object(mc_update_module.mc_command, "finish", finish_mock)

    event = MagicMock()
    event.group_id = 123456
    bot = MagicMock()

    before = data_manager.get_subscribed_groups()
    await handle_mc_command(bot, event, build_message_mock(""))
    assert data_manager.get_subscribed_groups() == before




@pytest.mark.asyncio
async def test_global_stop_does_not_fetch_manifest_or_advance_business_cursor(mocker):
    from xducraft_bot.shared.configuration import set_plugin_enabled

    bot = setup_http_and_bot(mocker, FAKE_API_DATA)
    write_state(groups=[123456], release_id="1.20.0", release_time="2024-01-01T00:00:00+00:00")
    before = data_manager.get_last_record("release")
    client = mc_update_module.httpx.AsyncClient
    set_plugin_enabled("mc_update", False)
    await check_update()
    client.assert_not_called()
    bot.send_group_msg.assert_not_awaited()
    assert data_manager.get_last_record("release") == before
