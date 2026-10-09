from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from xducraft_bot.plugins import xducraft_invite as invite
from xducraft_bot.plugins.xducraft_invite.api_client import GeneratedInvite
from xducraft_bot.plugins.xducraft_invite.data_manager import InviteStore
from xducraft_bot.plugins.xducraft_invite.settings import InviteSettings


GROUP_ID = 123456789
USER_ID = 233333
ADMIN_ID = 90001
CODE = "0123456789abcdef0123456789abcdef"


class HandlerFinished(Exception):
    pass


class FakePrivateEvent:
    def __init__(self, user_id: int = ADMIN_ID):
        self.user_id = user_id


class FakeGroupEvent:
    def __init__(self, group_id: int = GROUP_ID, user_id: int = USER_ID):
        self.group_id = group_id
        self.user_id = user_id


def _generated() -> GeneratedInvite:
    return GeneratedInvite(
        code=CODE,
        description="test",
        generated_at="2026-08-24 12:00:00",
    )


def _isolated_plugin(mocker, tmp_path):
    isolated_store = InviteStore(str(tmp_path / "invite.db"))
    settings = InviteSettings(
        group_id=GROUP_ID,
        api_url="https://example.test/invite",
        api_secret="secret",
    )
    mocker.patch.object(invite, "store", isolated_store)
    mocker.patch.object(invite, "SETTINGS", settings)
    client = MagicMock()
    client.generate = AsyncMock(return_value=_generated())
    mocker.patch.object(invite, "api_client", client)
    return isolated_store, client


@pytest.mark.asyncio
async def test_self_service_claims_before_delivery_and_cannot_issue_twice(mocker, tmp_path):
    isolated_store, client = _isolated_plugin(mocker, tmp_path)
    isolated_store.initialize([], initialized_at=100, initialized_by=ADMIN_ID)
    mocker.patch.object(invite, "_get_member_info", AsyncMock(return_value={"join_time": 101}))

    claim_state_at_private_send = []

    async def send_private_msg(**kwargs):
        claim_state_at_private_send.append(isolated_store.has_claim(USER_ID))
        return {"message_id": 1}

    bot = MagicMock()
    bot.send_private_msg = AsyncMock(side_effect=send_private_msg)
    bot.send_group_msg = AsyncMock(return_value={"message_id": 2})
    event = MagicMock()
    event.user_id = USER_ID
    event.group_id = GROUP_ID

    await invite.handle_self_service(bot, event)
    await invite.handle_self_service(bot, event)

    client.generate.assert_awaited_once_with(f"[自助]{USER_ID}")
    assert bot.send_private_msg.await_count == 2
    assert claim_state_at_private_send == [False, True]
    assert CODE in str(bot.send_private_msg.await_args_list[1].kwargs["message"])
    assert isolated_store.has_claim(USER_ID) is True
    assert isolated_store.stats().issuance_count == 1
    assert "已经申请过" in str(bot.send_group_msg.await_args.kwargs["message"])


@pytest.mark.asyncio
async def test_uncertain_final_delivery_still_permanently_claims_user(mocker, tmp_path):
    isolated_store, client = _isolated_plugin(mocker, tmp_path)
    isolated_store.initialize([], initialized_at=100, initialized_by=ADMIN_ID)
    mocker.patch.object(invite, "_get_member_info", AsyncMock(return_value={"join_time": 101}))

    bot = MagicMock()
    bot.send_private_msg = AsyncMock(side_effect=[{"message_id": 1}, RuntimeError("blocked")])
    bot.send_group_msg = AsyncMock(return_value={"message_id": 2})
    event = MagicMock()
    event.user_id = USER_ID
    event.group_id = GROUP_ID

    await invite.handle_self_service(bot, event)
    await invite.handle_self_service(bot, event)

    client.generate.assert_awaited_once_with(f"[自助]{USER_ID}")
    assert bot.send_private_msg.await_count == 2
    assert isolated_store.has_claim(USER_ID) is True
    assert isolated_store.stats().issuance_count == 1
    first_notice = bot.send_group_msg.await_args_list[0].kwargs["message"]
    assert "不能再次自助申请" in str(first_notice)


@pytest.mark.asyncio
async def test_admin_issue_requires_force_for_existing_record(mocker, tmp_path):
    isolated_store, client = _isolated_plugin(mocker, tmp_path)
    mocker.patch.object(invite, "PrivateMessageEvent", FakePrivateEvent)
    mocker.patch.object(invite, "_is_manager", AsyncMock(return_value=True))
    mocker.patch.object(invite, "_get_member_info", AsyncMock(return_value={"role": "member"}))
    finish = mocker.patch.object(
        invite.admin_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )

    bot = MagicMock()
    event = FakePrivateEvent()
    args = MagicMock()
    args.extract_plain_text.return_value = str(USER_ID)

    with pytest.raises(HandlerFinished):
        await invite.handle_admin(bot, event, args)

    client.generate.assert_awaited_once_with(f"[管理员发放]{USER_ID}")
    assert isolated_store.has_claim(USER_ID) is True
    assert CODE in finish.await_args.args[0]

    client.generate.reset_mock()
    finish.reset_mock()
    with pytest.raises(HandlerFinished):
        await invite.handle_admin(bot, event, args)

    client.generate.assert_not_awaited()
    assert "force" in finish.await_args.args[0]

    finish.reset_mock()
    args.extract_plain_text.return_value = f"force {USER_ID}"
    with pytest.raises(HandlerFinished):
        await invite.handle_admin(bot, event, args)

    client.generate.assert_awaited_once_with(f"[管理员发放]{USER_ID}")
    assert isolated_store.stats().claimed_count == 1
    assert isolated_store.stats().issuance_count == 2


@pytest.mark.asyncio
async def test_init_snapshots_current_members_and_opens_self_service(mocker, tmp_path):
    isolated_store, _ = _isolated_plugin(mocker, tmp_path)
    mocker.patch.object(invite, "PrivateMessageEvent", FakePrivateEvent)
    mocker.patch.object(invite, "is_superuser", AsyncMock(return_value=True))
    finish = mocker.patch.object(
        invite.admin_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )

    bot = MagicMock()
    bot.get_group_member_list = AsyncMock(return_value=[
        {"user_id": USER_ID, "join_time": 1},
        {"user_id": ADMIN_ID, "join_time": 1},
    ])
    args = MagicMock()
    args.extract_plain_text.return_value = "init"

    with pytest.raises(HandlerFinished):
        await invite.handle_admin(bot, FakePrivateEvent(), args)

    assert isolated_store.get_state().initialized is True
    assert isolated_store.get_state().self_service_enabled is True
    assert isolated_store.is_legacy(USER_ID) is True
    assert isolated_store.stats().legacy_count == 2
    assert "已快照 2 名旧成员" in finish.await_args.args[0]


@pytest.mark.asyncio
async def test_slash_invite_in_configured_group_runs_self_service(mocker):
    mocker.patch.object(invite, "GroupMessageEvent", FakeGroupEvent)
    mocker.patch.object(
        invite,
        "SETTINGS",
        InviteSettings(group_id=GROUP_ID, api_url="https://example.test", api_secret="secret"),
    )
    self_handler = mocker.patch.object(
        invite,
        "handle_self_service",
        AsyncMock(),
    )
    bot = MagicMock()
    event = FakeGroupEvent()
    args = MagicMock()
    args.extract_plain_text.return_value = ""

    await invite.handle_slash_self_service(bot, event, args)

    self_handler.assert_awaited_once_with(bot, event)



@pytest.mark.asyncio
async def test_private_slash_invite_guides_non_manager_to_configured_group(mocker):
    mocker.patch.object(invite, "PrivateMessageEvent", FakePrivateEvent)
    mocker.patch.object(
        invite,
        "SETTINGS",
        InviteSettings(group_id=GROUP_ID, api_url="https://example.test", api_secret="secret"),
    )
    mocker.patch.object(invite, "_is_manager", AsyncMock(return_value=False))
    finish = mocker.patch.object(
        invite.admin_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )
    args = MagicMock()
    args.extract_plain_text.return_value = ""

    with pytest.raises(HandlerFinished):
        await invite.handle_admin(MagicMock(), FakePrivateEvent(USER_ID), args)

    message = finish.await_args.args[0]
    assert str(GROUP_ID) in message
    assert "/邀请码" in message


@pytest.mark.asyncio
async def test_private_plain_invite_uses_same_group_guide(mocker):
    mocker.patch.object(
        invite,
        "SETTINGS",
        InviteSettings(group_id=GROUP_ID, api_url="https://example.test", api_secret="secret"),
    )
    finish = mocker.patch.object(
        invite.private_invite_guide,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )

    with pytest.raises(HandlerFinished):
        await invite.handle_private_invite_guide()

    message = finish.await_args.args[0]
    assert str(GROUP_ID) in message
    assert "/邀请码" in message
