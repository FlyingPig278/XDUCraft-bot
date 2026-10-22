"""统一的权限判定。

原先 ``is_admin`` 住在 ``xducraft_mc_status.utils`` 里，另外三个插件都从那里
import —— 词云插件依赖 MC 状态插件只是为了一个权限函数，这是明显的分层错误。
现在统一放在 shared 层，老位置保留一层再导出以兼容既有调用。
"""

from __future__ import annotations

from typing import Union

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.permission import SUPERUSER

ADMIN_ROLES = frozenset({"admin", "owner"})


async def is_superuser(bot: Bot, event: MessageEvent) -> bool:
    """是否是 NoneBot 配置里的 SUPERUSER。"""
    try:
        return await SUPERUSER(bot, event)
    except Exception:
        return False


async def is_admin(bot: Bot, event: Union[MessageEvent, GroupMessageEvent]) -> bool:
    """是否是超级用户、群主或群管理员。

    非群聊事件（私聊）只有 SUPERUSER 会返回 True。
    """
    if await is_superuser(bot, event):
        return True

    if not isinstance(event, GroupMessageEvent):
        return False

    sender = getattr(event, "sender", None)
    role = getattr(sender, "role", None) if sender is not None else None
    return role in ADMIN_ROLES


async def can_manage(bot: Bot, event: Union[MessageEvent, GroupMessageEvent]) -> bool:
    """管理类指令的统一入口。

    语义与 :func:`is_admin` 相同，单独留一个名字是为了让调用点读起来是
    “能不能管理”，而不是“是不是管理员”——将来若要放开某些角色，只改这里。
    """
    return await is_admin(bot, event)


async def can_manage_group(bot: Bot, event: MessageEvent, group_id: int) -> bool:
    """能否管理指定群，供私聊中的群级管理命令使用。

    群聊事件沿用消息携带的群角色；私聊事件必须再向 OneBot 查询目标群中的
    成员资料，不能仅凭用户提供的群号决定权限。SUPERUSER 不受群角色限制。
    """
    if await is_superuser(bot, event):
        return True

    if isinstance(event, GroupMessageEvent):
        if int(event.group_id) != int(group_id):
            return False
        sender = getattr(event, "sender", None)
        role = getattr(sender, "role", None) if sender is not None else None
        return role in ADMIN_ROLES

    try:
        member = await bot.get_group_member_info(
            group_id=int(group_id),
            user_id=int(event.user_id),
            no_cache=False,
        )
    except Exception:
        return False

    return str(member.get("role", "")).lower() in ADMIN_ROLES


__all__ = ["is_admin", "is_superuser", "can_manage", "can_manage_group", "ADMIN_ROLES"]
