from unittest.mock import AsyncMock, MagicMock

import pytest

from xducraft_bot.shared import permissions as permissions_module


@pytest.mark.asyncio
async def test_private_member_cannot_manage_selected_group(mocker):
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(return_value={"role": "member"})
    event = MagicMock()
    event.user_id = 10001
    mocker.patch.object(
        permissions_module,
        "is_superuser",
        AsyncMock(return_value=False),
    )

    allowed = await permissions_module.can_manage_group(
        bot,
        event,
        123456789,
    )

    assert allowed is False


@pytest.mark.asyncio
async def test_private_group_admin_can_manage_selected_group(mocker):
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(return_value={"role": "admin"})
    event = MagicMock()
    event.user_id = 10001
    mocker.patch.object(
        permissions_module,
        "is_superuser",
        AsyncMock(return_value=False),
    )

    allowed = await permissions_module.can_manage_group(
        bot,
        event,
        123456789,
    )

    assert allowed is True
    bot.get_group_member_info.assert_awaited_once_with(
        group_id=123456789,
        user_id=10001,
        no_cache=False,
    )
