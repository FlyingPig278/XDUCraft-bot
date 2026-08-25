"""自动接受指定群成员发来的好友申请。

OneBot v11 的好友申请事件不包含来源群号，因此插件会查询申请人当前是否属于部署配置
中的群。只有该群同时在统一功能管理中开启时，申请才会被自动接受。
"""

from __future__ import annotations

from typing import Optional

from nonebot import on_request
from nonebot.adapters.onebot.v11 import Bot, FriendRequestEvent
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from xducraft_bot.shared import feature_gate

from .settings import SETTINGS


__plugin_meta__ = PluginMetadata(
    name="XDUCraft_auto_friend",
    description="自动接受配置白名单群成员发来的好友申请",
    usage="在 .env 配置群号，再由群管理员使用 /功能 on 自动加好友 开启",
)

FEATURE_KEY = "auto_accept_friend"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="自动加好友",
    description="自动接受部署配置白名单中本群成员发来的好友申请",
    default_enabled=False,
    passive=True,
))

friend_request = on_request(
    priority=10,
    block=False,
    rule=Rule(lambda event: isinstance(event, FriendRequestEvent)),
)


async def _find_source_group(bot: Bot, user_id: int) -> Optional[int]:
    """返回申请人所属的首个已配置且已启用群；查询失败时保持拒绝。"""
    for group_id in SETTINGS.group_ids:
        if not feature_gate.is_enabled(FEATURE_KEY, group_id):
            continue
        try:
            member = await bot.get_group_member_info(
                group_id=group_id,
                user_id=int(user_id),
                no_cache=False,
            )
        except Exception as exc:
            logger.debug(
                "[AutoFriend] 无法确认用户 {} 是否属于群 {}: {}",
                user_id,
                group_id,
                exc,
            )
            continue
        if not isinstance(member, dict):
            continue
        try:
            member_user_id = int(member["user_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if member_user_id == int(user_id):
            return group_id
    return None


@friend_request.handle()
async def handle_friend_request(bot: Bot, event: FriendRequestEvent) -> None:
    group_id = await _find_source_group(bot, event.user_id)
    if group_id is None:
        return

    try:
        await bot.set_friend_add_request(flag=event.flag, approve=True)
    except Exception as exc:
        logger.warning(
            "[AutoFriend] 自动接受用户 {} 的好友申请失败（匹配群 {}）: {}",
            event.user_id,
            group_id,
            exc,
        )
        return

    logger.info(
        "[AutoFriend] 已自动接受用户 {} 的好友申请（匹配群 {}）。",
        event.user_id,
        group_id,
    )


__all__ = ["FEATURE_KEY", "handle_friend_request"]
