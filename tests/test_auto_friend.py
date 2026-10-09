from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from xducraft_bot.plugins import xducraft_auto_friend as auto_friend
from xducraft_bot.plugins.xducraft_auto_friend.settings import (
    AutoFriendSettings,
    _normalize_group_ids,
)


GROUP_A = 123456789
GROUP_B = 987654321
USER_ID = 233333


def _event():
    event = MagicMock()
    event.user_id = USER_ID
    event.flag = "friend-request-flag"
    return event


@pytest.mark.asyncio
async def test_accepts_member_from_configured_enabled_group(mocker):
    mocker.patch.object(
        auto_friend,
        "SETTINGS",
        AutoFriendSettings(group_ids=(GROUP_A, GROUP_B)),
    )
    mocker.patch.object(
        auto_friend.feature_gate,
        "is_enabled",
        side_effect=lambda key, group_id: group_id == GROUP_B,
    )
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(
        return_value={"group_id": GROUP_B, "user_id": USER_ID}
    )
    bot.set_friend_add_request = AsyncMock()

    await auto_friend.handle_friend_request(bot, _event())

    bot.get_group_member_info.assert_awaited_once_with(
        group_id=GROUP_B,
        user_id=USER_ID,
        no_cache=False,
    )
    bot.set_friend_add_request.assert_awaited_once_with(
        flag="friend-request-flag",
        approve=True,
    )


@pytest.mark.asyncio
async def test_does_not_query_or_accept_when_feature_is_disabled(mocker):
    mocker.patch.object(
        auto_friend,
        "SETTINGS",
        AutoFriendSettings(group_ids=(GROUP_A,)),
    )
    mocker.patch.object(auto_friend.feature_gate, "is_enabled", return_value=False)
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock()
    bot.set_friend_add_request = AsyncMock()

    await auto_friend.handle_friend_request(bot, _event())

    bot.get_group_member_info.assert_not_awaited()
    bot.set_friend_add_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_failure_is_fail_closed_and_next_group_can_match(mocker):
    mocker.patch.object(
        auto_friend,
        "SETTINGS",
        AutoFriendSettings(group_ids=(GROUP_A, GROUP_B)),
    )
    mocker.patch.object(auto_friend.feature_gate, "is_enabled", return_value=True)
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(
        side_effect=[RuntimeError("not a member"), {"user_id": USER_ID}]
    )
    bot.set_friend_add_request = AsyncMock()

    await auto_friend.handle_friend_request(bot, _event())

    assert bot.get_group_member_info.await_count == 2
    bot.set_friend_add_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_does_not_accept_when_member_response_is_for_another_user(mocker):
    mocker.patch.object(
        auto_friend,
        "SETTINGS",
        AutoFriendSettings(group_ids=(GROUP_A,)),
    )
    mocker.patch.object(auto_friend.feature_gate, "is_enabled", return_value=True)
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(return_value={"user_id": USER_ID + 1})
    bot.set_friend_add_request = AsyncMock()

    await auto_friend.handle_friend_request(bot, _event())

    bot.set_friend_add_request.assert_not_awaited()




def test_group_id_config_removes_invalid_and_duplicate_values():
    assert _normalize_group_ids([0, GROUP_A, -1, GROUP_A, GROUP_B]) == (
        GROUP_A,
        GROUP_B,
    )
