"""OneBot v11 发送辅助。

集中处理三件在各插件里反复出现、且每次都写得不太一样的事：

1. 合并转发节点的构造与发送（群聊 / 私聊 API 名字不同，且都可能失败）；
2. 失败回退：合并转发被风控时退化成普通消息，而不是整条指令报错；
3. “安静回执”：管理类操作的结果私聊发给操作者，不在大群里刷屏。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.log import logger

# QQ 对单条合并转发的节点数量有限制，超过就整条发不出去。
MAX_FORWARD_NODES = 100

MessageLike = Union[str, Message, MessageSegment]


def make_node(content: MessageLike, name: str, uin: Union[int, str]) -> Dict[str, Any]:
    """构造一个合并转发节点。

    ``name``/``uin`` 决定转发卡片里显示的发送者，反撤回插件靠这两个字段
    保住“谁说的”这一信息。
    """
    return {
        "type": "node",
        "data": {
            "name": str(name),
            "uin": str(uin),
            "content": content,
        },
    }


def chunk_nodes(nodes: Sequence[Dict[str, Any]], size: int = MAX_FORWARD_NODES) -> List[List[Dict[str, Any]]]:
    """把过长的节点列表切成多条合并转发。"""
    size = max(1, int(size))
    return [list(nodes[index:index + size]) for index in range(0, len(nodes), size)]


async def send_group_forward(bot: Bot, group_id: int, nodes: Sequence[Dict[str, Any]]) -> bool:
    """向群发送合并转发（自动分批）。返回是否全部成功。"""
    if not nodes:
        return False
    for batch in chunk_nodes(nodes):
        try:
            await bot.send_group_forward_msg(group_id=int(group_id), messages=batch)
        except Exception as exc:
            logger.warning("[OneBot] 群 {} 合并转发失败: {}", group_id, exc)
            return False
    return True


async def send_private_forward(bot: Bot, user_id: int, nodes: Sequence[Dict[str, Any]]) -> bool:
    """向私聊发送合并转发（自动分批）。返回是否全部成功。"""
    if not nodes:
        return False
    for batch in chunk_nodes(nodes):
        try:
            await bot.call_api("send_private_forward_msg", user_id=int(user_id), messages=batch)
        except Exception as exc:
            logger.warning("[OneBot] 私聊 {} 合并转发失败: {}", user_id, exc)
            return False
    return True


async def send_forward_to_event(bot: Bot, event: MessageEvent, nodes: Sequence[Dict[str, Any]]) -> bool:
    """按事件来源选择群聊 / 私聊合并转发。"""
    if isinstance(event, GroupMessageEvent):
        return await send_group_forward(bot, event.group_id, nodes)
    return await send_private_forward(bot, event.user_id, nodes)


async def send_text_sections(
    bot: Bot,
    event: MessageEvent,
    sections: Iterable[str],
    *,
    title: str,
    fallback_separator: str = "\n\n",
) -> bool:
    """把多段文本以合并转发发出；失败时回退为一条普通消息。

    帮助、列表这类“长文本”统一走这里：正常情况下是一张干净的转发卡片，
    被风控时也不会变成“什么都没发出去”。
    """
    section_list = [section.strip() for section in sections if section and section.strip()]
    if not section_list:
        return False

    self_id = getattr(event, "self_id", 0)
    nodes = [make_node(section, title, self_id) for section in section_list]

    if await send_forward_to_event(bot, event, nodes):
        return True

    plain = fallback_separator.join(section_list)
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_msg(group_id=event.group_id, message=plain)
        else:
            await bot.send_private_msg(user_id=event.user_id, message=plain)
        return True
    except Exception as exc:
        logger.warning("[OneBot] 回退普通消息也失败: {}", exc)
        return False


async def notify_privately(bot: Bot, user_id: int, message: MessageLike) -> bool:
    """私聊发送一条消息，失败只记日志不抛异常。"""
    try:
        await bot.send_private_msg(user_id=int(user_id), message=message)
        return True
    except Exception as exc:
        logger.info("[OneBot] 私聊 {} 发送失败（多半是没加好友）: {}", user_id, exc)
        return False


async def reply_quietly(
    bot: Bot,
    event: MessageEvent,
    message: MessageLike,
    *,
    quiet: bool,
    group_hint: Optional[str] = None,
) -> None:
    """管理类操作的回执。

    ``quiet`` 为真时优先私聊操作者，避免在大群里刷屏；私聊失败（没加好友）
    才退回群里，保证操作者一定看得到结果。

    Args:
        group_hint: 安静模式下**确实**需要在群里留一句时的极简提示；
            为 None 表示群里什么都不发。
    """
    if not quiet or not isinstance(event, GroupMessageEvent):
        try:
            await bot.send(event, message)
        except Exception as exc:
            logger.warning("[OneBot] 回执发送失败: {}", exc)
        return

    if await notify_privately(bot, event.user_id, message):
        if group_hint:
            try:
                await bot.send(event, group_hint)
            except Exception:
                pass
        return

    # 私聊不通，只能退回群里，否则操作者收不到任何反馈。
    try:
        await bot.send(event, message)
    except Exception as exc:
        logger.warning("[OneBot] 回执发送失败: {}", exc)


def extract_group_id(event: MessageEvent) -> Optional[int]:
    """群聊事件返回群号，私聊返回 None。"""
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        return None
    try:
        return int(group_id)
    except (TypeError, ValueError):
        return None


__all__ = [
    "MAX_FORWARD_NODES",
    "make_node",
    "chunk_nodes",
    "send_group_forward",
    "send_private_forward",
    "send_forward_to_event",
    "send_text_sections",
    "notify_privately",
    "reply_quietly",
    "extract_group_id",
]
