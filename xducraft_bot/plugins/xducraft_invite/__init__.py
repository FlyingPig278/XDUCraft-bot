"""XDUCraft 邀请码自助与私聊管理。"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from nonebot import get_driver, on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from xducraft_bot.shared.onebot import notify_privately
from xducraft_bot.shared.permissions import can_manage_group, is_superuser


from . import texts as text
from .api_client import GeneratedInvite, InviteApiClient, InviteApiError
from .data_manager import ACQUIRED, ALREADY_CLAIMED, IN_PROGRESS, InviteStore, store
from .settings import SETTINGS, InviteSettings

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_invite",
    description=text.PLUGIN_DESCRIPTION,
    usage=text.PLUGIN_USAGE,
)

SELF_REMARK_PREFIX = text.SELF_REMARK_PREFIX
ADMIN_REMARK_PREFIX = text.ADMIN_REMARK_PREFIX
SELF_PRECHECK_MESSAGE = text.SELF_PRECHECK_MESSAGE


async def _is_self_request(event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    if SETTINGS.group_id <= 0 or int(event.group_id) != SETTINGS.group_id:
        return False
    return bool(event.is_tome() and event.get_plaintext().strip() == text.INVITE_COMMAND_NAME)


async def _is_private_plain_invite(event: MessageEvent) -> bool:
    return bool(
        isinstance(event, PrivateMessageEvent)
        and event.get_plaintext().strip() == text.INVITE_COMMAND_NAME
    )


async def _is_group_command(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent)


async def _is_private_command(event: MessageEvent) -> bool:
    return isinstance(event, PrivateMessageEvent)


self_service = on_message(rule=Rule(_is_self_request), priority=5, block=True)
slash_self_service = on_command(
    text.INVITE_COMMAND_NAME,
    rule=Rule(_is_group_command),
    priority=5,
    block=True,
)
private_invite_guide = on_message(rule=Rule(_is_private_plain_invite), priority=5, block=True)
admin_command = on_command(
    "invite",
    aliases={text.INVITE_COMMAND_NAME},
    rule=Rule(_is_private_command),
    priority=5,
    block=True,
)
api_client = InviteApiClient(SETTINGS.api_url, SETTINGS.api_secret)


@get_driver().on_shutdown
async def _close_api_client() -> None:
    await api_client.aclose()


def _notice(user_id: int, text: str) -> Message:
    return Message([MessageSegment.at(int(user_id)), MessageSegment.text(f" {text}")])


def _self_service_guide() -> str:
    return text.self_service_guide(SETTINGS.group_id)


async def _send_group_notice(bot: Bot, group_id: int, user_id: int, text: str) -> None:
    try:
        await bot.send_group_msg(
            group_id=int(group_id),
            message=_notice(user_id, text),
        )
    except Exception as exc:
        logger.warning("[Invite] 群 {} 回执发送失败: {}", group_id, exc)


async def _get_member_info(bot: Bot, user_id: int) -> Optional[Dict[str, Any]]:
    try:
        member = await bot.get_group_member_info(
            group_id=SETTINGS.group_id,
            user_id=int(user_id),
            no_cache=False,
        )
    except Exception as exc:
        logger.info("[Invite] 无法查询群 {} 成员 {}: {}", SETTINGS.group_id, user_id, exc)
        return None
    return member if isinstance(member, dict) else None


async def _is_manager(bot: Bot, event: MessageEvent) -> bool:
    if await is_superuser(bot, event):
        return True
    if SETTINGS.group_id <= 0:
        return False
    return await can_manage_group(bot, event, SETTINGS.group_id)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0




def _status_text(settings: InviteSettings, invite_store: InviteStore) -> str:
    stats = invite_store.stats()
    state = stats.state
    return text.render_status(
        initialized=state.initialized,
        enabled=state.self_service_enabled,
        group_id=settings.group_id,
        initialized_at=state.initialized_at,
        legacy_count=stats.legacy_count,
        claimed_count=stats.claimed_count,
        issuance_count=stats.issuance_count,
        secret_configured=bool(settings.api_secret),
    )


async def _generate(remark: str) -> GeneratedInvite:
    return await api_client.generate(remark)


@self_service.handle()
async def handle_self_service(bot: Bot, event: GroupMessageEvent) -> None:
    user_id = int(event.user_id)
    group_id = int(event.group_id)
    state = store.get_state()

    if not state.initialized:
        await _send_group_notice(bot, group_id, user_id, text.SELF_NOT_INITIALIZED)
        return
    if not state.self_service_enabled:
        await _send_group_notice(bot, group_id, user_id, text.SELF_DISABLED)
        return

    member = await _get_member_info(bot, user_id)
    if member is None:
        await _send_group_notice(bot, group_id, user_id, text.SELF_MEMBER_UNKNOWN)
        return
    if store.is_legacy(user_id):
        await _send_group_notice(
            bot,
            group_id,
            user_id,
            text.SELF_LEGACY_MEMBER,
        )
        return

    join_time = _safe_int(member.get("join_time"))
    if join_time <= 0:
        await _send_group_notice(bot, group_id, user_id, text.SELF_JOIN_TIME_UNKNOWN)
        return
    if state.initialized_at is None or join_time < state.initialized_at:
        await _send_group_notice(
            bot,
            group_id,
            user_id,
            text.SELF_JOINED_TOO_EARLY,
        )
        return

    lease = store.acquire_lease(
        user_id,
        source="self",
        operator_id=user_id,
    )
    if lease == ALREADY_CLAIMED:
        await _send_group_notice(bot, group_id, user_id, text.SELF_ALREADY_CLAIMED)
        return
    if lease == IN_PROGRESS:
        await _send_group_notice(bot, group_id, user_id, text.SELF_IN_PROGRESS)
        return
    if lease != ACQUIRED:
        await _send_group_notice(bot, group_id, user_id, text.SELF_BUSY)
        return

    if not await notify_privately(bot, user_id, SELF_PRECHECK_MESSAGE):
        store.release_lease(user_id)
        await _send_group_notice(
            bot,
            group_id,
            user_id,
            text.SELF_PRIVATE_UNAVAILABLE,
        )
        return

    try:
        generated = await _generate(f"{SELF_REMARK_PREFIX}{user_id}")
    except InviteApiError as exc:
        store.release_lease(user_id)
        logger.warning("[Invite] 用户 {} 自助发码失败: {}", user_id, exc.message)
        await _send_group_notice(bot, group_id, user_id, text.SELF_GENERATE_FAILED)
        return
    except Exception as exc:
        store.release_lease(user_id)
        logger.exception("[Invite] 用户 {} 自助发码发生未预期错误: {}", user_id, exc)
        await _send_group_notice(bot, group_id, user_id, text.SELF_GENERATE_FAILED)
        return

    # 先永久占用自助资格，再发送邀请码。这样即使私聊调用结果不确定或进程
    # 在发送后崩溃，玩家也无法通过自助入口拿到第二个码。
    try:
        store.record_success(
            user_id,
            source="self",
            group_id=group_id,
            operator_id=user_id,
            forced=False,
            api_generated_at=generated.generated_at,
        )
    except Exception as exc:
        logger.exception("[Invite] 用户 {} 邀请码已生成，但领取记录落库失败: {}", user_id, exc)
        try:
            store.release_lease(user_id)
        except Exception:
            pass
        await _send_group_notice(bot, group_id, user_id, text.SELF_PERSIST_FAILED_RETRY)
        return

    delivered = await notify_privately(
        bot,
        user_id,
        text.self_invite_message(generated.code),
    )
    if not delivered:
        # 发送结果可能不确定，领取记录必须保留；只有管理员 force 可以补发。
        await _send_group_notice(bot, group_id, user_id, text.SELF_DELIVERY_FAILED_LOCKED)
        return

    await _send_group_notice(bot, group_id, user_id, text.SELF_SUCCESS_GROUP)


@slash_self_service.handle()
async def handle_slash_self_service(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> None:
    if args.extract_plain_text().strip():
        await slash_self_service.finish(text.GROUP_ARGUMENTS_REJECTED)
    if int(event.group_id) == SETTINGS.group_id:
        await handle_self_service(bot, event)
        return
    await slash_self_service.finish(_self_service_guide())


@private_invite_guide.handle()
async def handle_private_invite_guide() -> None:
    await private_invite_guide.finish(_self_service_guide())


async def _handle_init(bot: Bot, event: PrivateMessageEvent) -> None:
    if not await is_superuser(bot, event):
        await admin_command.finish(text.ADMIN_INIT_SUPERUSER_ONLY)

    config_error = SETTINGS.configuration_error()
    if config_error:
        await admin_command.finish(text.init_config_error(config_error))
    if store.get_state().initialized:
        await admin_command.finish(text.ADMIN_ALREADY_INITIALIZED)

    try:
        members = await bot.get_group_member_list(group_id=SETTINGS.group_id)
    except Exception as exc:
        logger.warning("[Invite] 初始化时读取群成员失败: {}", exc)
        await admin_command.finish(text.ADMIN_MEMBER_LIST_FAILED)
    if not isinstance(members, list) or not members:
        await admin_command.finish(text.ADMIN_MEMBER_LIST_EMPTY)

    legacy_ids = {
        _safe_int(member.get("user_id"))
        for member in members
        if isinstance(member, dict) and _safe_int(member.get("user_id")) > 0
    }
    initialized_at = int(time.time())
    if not store.initialize(legacy_ids, initialized_at, int(event.user_id)):
        await admin_command.finish(text.ADMIN_ALREADY_INITIALIZED)
    await admin_command.finish(text.init_success(len(legacy_ids), initialized_at))


async def _handle_admin_issue(
    bot: Bot,
    event: PrivateMessageEvent,
    target_user_id: int,
    *,
    forced: bool,
) -> None:
    config_error = SETTINGS.configuration_error()
    if config_error:
        await admin_command.finish(text.issue_config_error(config_error))

    member = await _get_member_info(bot, target_user_id)
    if member is None:
        await admin_command.finish(text.target_not_member(target_user_id))

    lease = store.acquire_lease(
        target_user_id,
        source="admin",
        operator_id=int(event.user_id),
        allow_claimed=forced,
    )
    if lease == ALREADY_CLAIMED:
        await admin_command.finish(text.target_already_claimed(target_user_id))
    if lease == IN_PROGRESS:
        await admin_command.finish(text.target_in_progress(target_user_id))
    if lease != ACQUIRED:
        await admin_command.finish(text.ADMIN_LEASE_BUSY)

    try:
        generated = await _generate(f"{ADMIN_REMARK_PREFIX}{target_user_id}")
    except InviteApiError as exc:
        store.release_lease(target_user_id)
        await admin_command.finish(text.api_generate_failed(exc.message))
    except Exception as exc:
        store.release_lease(target_user_id)
        logger.exception("[Invite] 管理员为 {} 发码发生未预期错误: {}", target_user_id, exc)
        await admin_command.finish(text.ADMIN_GENERATE_INTERNAL_ERROR)

    try:
        store.record_success(
            target_user_id,
            source="admin",
            group_id=SETTINGS.group_id,
            operator_id=int(event.user_id),
            forced=forced,
            api_generated_at=generated.generated_at,
        )
    except Exception as exc:
        logger.exception("[Invite] 管理员为 {} 生成邀请码后落库失败: {}", target_user_id, exc)
        await admin_command.finish(text.ADMIN_PERSIST_FAILED)

    await admin_command.finish(
        text.admin_issue_success(target_user_id, generated.code, forced=forced)
    )


@admin_command.handle()
async def handle_admin(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    if not isinstance(event, PrivateMessageEvent):
        await admin_command.finish(text.ADMIN_PRIVATE_ONLY)

    tokens = args.extract_plain_text().strip().split()
    action = tokens[0].lower() if tokens else ""

    if not tokens:
        if await _is_manager(bot, event):
            await admin_command.finish(text.ADMIN_USAGE)
        await admin_command.finish(_self_service_guide())

    if action == "init":
        if len(tokens) != 1:
            await admin_command.finish(text.USAGE_INIT)
        await _handle_init(bot, event)
        return

    if not await _is_manager(bot, event):
        await admin_command.finish(text.ADMIN_PERMISSION_DENIED)

    if action == "status":
        if len(tokens) != 1:
            await admin_command.finish(text.USAGE_STATUS)
        await admin_command.finish(_status_text(SETTINGS, store))

    if action in {"on", "off"}:
        if len(tokens) != 1:
            await admin_command.finish(text.usage_toggle(action))
        enabled = action == "on"
        if not store.set_self_service_enabled(enabled):
            await admin_command.finish(text.ADMIN_NOT_INITIALIZED)
        await admin_command.finish(text.toggle_success(enabled))

    if action == "force":
        if len(tokens) != 2 or not tokens[1].isdigit():
            await admin_command.finish(text.USAGE_FORCE)
        await _handle_admin_issue(bot, event, int(tokens[1]), forced=True)
        return

    if len(tokens) == 1 and tokens[0].isdigit():
        await _handle_admin_issue(bot, event, int(tokens[0]), forced=False)
        return

    await admin_command.finish(text.ADMIN_USAGE)


__all__ = [
    "ADMIN_REMARK_PREFIX",
    "SELF_REMARK_PREFIX",
    "SELF_PRECHECK_MESSAGE",
    "handle_admin",
    "handle_private_invite_guide",
    "handle_slash_self_service",
    "handle_self_service",
]
