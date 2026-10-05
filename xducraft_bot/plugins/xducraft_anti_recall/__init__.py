"""反撤回。

记录已启用群里被撤回的消息，并**通过私聊**以合并转发的形式提供查询。

设计上的几个取舍：

- **不在群里播报。** 撤回被当场喊出来最容易引战，而且是典型的刷屏来源。
  记录只在私聊里查得到，群里一声不响。
- **只在启用的群里记录。** 未启用的群连消息缓存都不会写。
- **私聊查询要校验群成员身份。** 否则任何人都能翻到任意群的撤回内容。

指令（群内，管理员）::

    /反撤回 on|off      开关本群
    /反撤回 status      查看状态
    /反撤回 clear       清空本群记录

指令（私聊）::

    /撤回               单群直接展示，多群返回数字选择菜单
    /撤回 <群号> [条数]  指定群和条数

多群菜单在两分钟内接受一条纯数字私聊回复。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from nonebot import on_command, on_message, on_notice, require
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, GroupRecallNoticeEvent, Message, MessageEvent, MessageSegment,
    PrivateMessageEvent,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.onebot import MAX_FORWARD_NODES, make_node
from xducraft_bot.shared.permissions import can_manage, is_superuser

from .data_manager import MEDIA_DIR, message_id_variants, store
from .message_codec import decode_forward_nodes, decode_message, download_media, encode_message

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_anti_recall",
    description="记录群消息撤回，支持图片/表情包/合并转发，私聊查询",
    usage="群内：/反撤回 on|off|status|clear\n私聊：/撤回 [群号] [条数]",
)

FEATURE_KEY = "anti_recall"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="反撤回",
    description="记录本群被撤回的消息（仅私聊可查，群内不播报）",
    default_enabled=False,
    passive=True,
))


def _group_enabled(event: GroupMessageEvent) -> bool:
    return feature_gate.is_enabled(FEATURE_KEY, event.group_id)


# 记录器必须先于会 block 的命令运行，否则命令消息被撤回时永远不在缓存里。
# 它自身不 block，记录完仍会正常交给其他插件。
message_recorder = on_message(
    priority=1,
    block=False,
    rule=Rule(lambda event: isinstance(event, GroupMessageEvent)),
)
recall_listener = on_notice(
    priority=98,
    block=False,
    rule=Rule(lambda event: isinstance(event, GroupRecallNoticeEvent)),
)
admin_command = on_command("反撤回", aliases={"antirecall", "anti_recall"}, priority=10, block=True)
query_command = on_command("撤回", aliases={"recall", "查撤回"}, priority=10, block=True)


# ==============================================================================
# 记录
# ==============================================================================

@message_recorder.handle()
async def handle_record(bot: Bot, event: GroupMessageEvent):
    """把群消息写进缓存，等着它可能被撤回。"""
    if not _group_enabled(event):
        return
    if store.is_user_exempt(event.user_id):
        return

    config = store.get_config()
    if not config["include_self"] and str(event.user_id) == str(event.self_id):
        return

    sender = event.sender
    sender_name = (getattr(sender, "card", "") or getattr(sender, "nickname", "") or str(event.user_id))

    try:
        content = await encode_message(event.message, bot)
    except Exception as exc:
        logger.debug("[AntiRecall] 编码消息失败 {}: {}", event.message_id, exc)
        return

    if not content:
        return

    try:
        store.cache_message(
            group_id=event.group_id,
            message_id=event.message_id,
            user_id=event.user_id,
            sender_name=sender_name,
            content=content,
            sent_at=int(getattr(event, "time", 0) or time.time()),
        )
    except Exception as exc:
        logger.warning("[AntiRecall] 缓存消息失败: {}", exc)


def _message_from_api_payload(raw_message: Any) -> Message:
    """把 OneBot API 返回的消息段字典转换成适配器的 ``Message``。"""
    if isinstance(raw_message, Message):
        return raw_message
    if isinstance(raw_message, dict):
        raw_message = [raw_message]
    if isinstance(raw_message, (list, tuple)):
        message = Message()
        for item in raw_message:
            if isinstance(item, MessageSegment):
                message += item
            elif isinstance(item, dict) and item.get("type"):
                data = item.get("data") if isinstance(item.get("data"), dict) else {}
                message += MessageSegment(str(item["type"]), data)
            else:
                message += Message(str(item))
        return message
    return Message(raw_message)


async def _recover_recalled_message(
    bot: Bot,
    event: GroupRecallNoticeEvent,
) -> Optional[Dict[str, Any]]:
    """先查本地缓存；未命中时趁撤回事件刚到，尽力向协议端补取原消息。"""
    cached = store.find_cached_message(event.group_id, event.message_id, event.user_id)
    if cached is not None:
        return cached

    # NapCat 某些路径会把同一个 32 位 ID 分别按有符号/无符号整数上报。
    for message_id in message_id_variants(event.message_id):
        try:
            payload = await bot.get_msg(message_id=message_id)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload_group = payload.get("group_id")
        if payload_group not in (None, ""):
            try:
                if int(payload_group) != int(event.group_id):
                    continue
            except (TypeError, ValueError):
                continue

        raw_message = payload.get("message", payload.get("raw_message"))
        if raw_message is None:
            continue
        try:
            message = _message_from_api_payload(raw_message)
            content = await encode_message(message, bot)
        except Exception as exc:
            logger.debug("[AntiRecall] 补取消息 {} 后编码失败: {}", message_id, exc)
            continue
        if not content:
            continue

        sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
        try:
            user_id = int(sender.get("user_id") or payload.get("user_id") or event.user_id)
        except (TypeError, ValueError):
            continue
        if user_id != int(event.user_id):
            continue
        sender_name = (
            sender.get("card")
            or sender.get("nickname")
            or payload.get("sender_name")
            or str(user_id)
        )
        logger.info(
            "[AntiRecall] 群 {} 的撤回消息 {} 未命中缓存，已从协议端补取。",
            event.group_id,
            event.message_id,
        )
        return {
            "message_id": int(payload.get("message_id") or message_id),
            "group_id": int(event.group_id),
            "user_id": user_id,
            "sender_name": str(sender_name),
            "sent_at": int(payload.get("time") or getattr(event, "time", 0) or time.time()),
            "content": content,
        }
    return None


@recall_listener.handle()
async def handle_recall(bot: Bot, event: GroupRecallNoticeEvent):
    """收到撤回通知：固化记录，并趁 URL 还没失效把图片抓下来。"""
    if not feature_gate.is_enabled(FEATURE_KEY, event.group_id):
        return

    cached = await _recover_recalled_message(bot, event)
    if cached is None:
        logger.warning(
            "[AntiRecall] 无法恢复群 {} 的撤回消息 {}（发送者 {}，操作者 {}）。",
            event.group_id,
            event.message_id,
            event.user_id,
            getattr(event, "operator_id", 0),
        )
        return

    if store.is_user_exempt(cached["user_id"]):
        return

    record_message_id = cached["message_id"]
    created = store.record_recall(
        group_id=event.group_id,
        message_id=record_message_id,
        user_id=cached["user_id"],
        sender_name=cached["sender_name"],
        operator_id=int(getattr(event, "operator_id", 0) or 0),
        sent_at=cached["sent_at"],
        content=cached["content"],
    )
    if not created:
        return

    config = store.get_config()
    if not config["save_media"]:
        return

    try:
        # 撤回通常发生在发出后两分钟内，此刻 URL 还有效；等用户来查就晚了。
        if await download_media(cached["content"], store, config["max_media_mb"] * 1024 * 1024):
            store.update_recall_content(event.group_id, record_message_id, cached["content"])
    except Exception as exc:
        logger.debug("[AntiRecall] 保存撤回媒体失败: {}", exc)


# ==============================================================================
# 群内管理指令
# ==============================================================================

@admin_command.handle()
async def handle_admin(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await admin_command.finish("这条命令请在群里使用。查询撤回消息请发送 /撤回。")

    if not await can_manage(bot, event):
        await admin_command.finish("只有群管理员可以配置反撤回。")

    arg_list = args.extract_plain_text().strip().split()
    action = arg_list[0].lower() if arg_list else "status"
    group_id = event.group_id

    if action in {"on", "开", "开启", "启用"}:
        changed = feature_gate.set_enabled(FEATURE_KEY, group_id, True)
        await admin_command.finish(
            ("已开启本群反撤回。" if changed else "本群反撤回已经是开启状态。")
            + "\n撤回内容只能私聊机器人发送 /撤回 查看，群里不会播报。"
        )

    if action in {"off", "关", "关闭", "停用"}:
        changed = feature_gate.set_enabled(FEATURE_KEY, group_id, False)
        await admin_command.finish(
            "已关闭本群反撤回，不再记录任何消息。" if changed else "本群反撤回已经是关闭状态。"
        )

    if action in {"clear", "清空"}:
        removed = store.purge_group(group_id)
        await admin_command.finish(f"已清空本群的 {removed} 条撤回记录及消息缓存。")

    if action in {"status", "状态"}:
        enabled, source = feature_gate.resolve(FEATURE_KEY, group_id)
        config = store.get_config()
        await admin_command.finish(
            f"本群反撤回：{'开启' if enabled else '关闭'}"
            f"（{'本群配置' if source == feature_gate.SOURCE_GROUP else '默认值'}）\n"
            f"已记录：{store.count_recalls(group_id)} 条\n"
            f"保留期：撤回记录 {config['recall_retention_days']} 天，消息缓存 {config['cache_retention_hours']} 小时\n"
            f"保存图片：{'是' if config['save_media'] else '否'}\n"
            "查询方式：私聊机器人发送 /撤回"
        )

    await admin_command.finish("用法：/反撤回 on|off|status|clear")


# ==============================================================================
# 私聊查询
# ==============================================================================
#: (user_id, group_id) -> (是否是成员, 校验时间)
_membership_cache: Dict[Tuple[int, int], Tuple[bool, float]] = {}
MEMBERSHIP_TTL = 300.0

#: (bot_id, user_id) -> (失效时间, 菜单中的群号)
_pending_group_selections: Dict[Tuple[int, int], Tuple[float, List[int]]] = {}
SELECTION_TTL = 120.0
_SELECTION_CANCEL_WORDS = {"取消", "/取消", "cancel", "/cancel"}


async def _is_group_member(bot: Bot, user_id: int, group_id: int) -> bool:
    """校验用户确实在群里——否则任何人都能翻到任意群的撤回内容。"""
    key = (int(user_id), int(group_id))
    cached = _membership_cache.get(key)
    now = time.monotonic()
    if cached is not None and now - cached[1] < MEMBERSHIP_TTL:
        return cached[0]

    try:
        await bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id), no_cache=False)
        result = True
    except Exception:
        result = False

    _membership_cache[key] = (result, now)
    if len(_membership_cache) > 4096:
        _membership_cache.clear()
    return result


async def _visible_group_stats(bot: Bot, user_id: int, allow_all: bool) -> List[Dict[str, int]]:
    """该用户能查看的群及其撤回记录数，按最近撤回时间排序。"""
    candidates = store.list_recent_recall_group_stats(limit=30)
    if allow_all:
        return candidates

    visible = []
    for item in candidates:
        if await _is_group_member(bot, user_id, item["group_id"]):
            visible.append(item)
    return visible


def _selection_key(event: PrivateMessageEvent) -> Tuple[int, int]:
    return int(event.self_id), int(event.user_id)


def _get_pending_selection(event: PrivateMessageEvent) -> Optional[List[int]]:
    key = _selection_key(event)
    pending = _pending_group_selections.get(key)
    if pending is None:
        return None
    expires_at, group_ids = pending
    if time.monotonic() >= expires_at:
        _pending_group_selections.pop(key, None)
        return None
    return group_ids


def _is_selection_reply(event: MessageEvent) -> bool:
    if not isinstance(event, PrivateMessageEvent) or _get_pending_selection(event) is None:
        return False
    text = event.get_plaintext().strip().lower()
    return text.isdigit() or text in _SELECTION_CANCEL_WORDS


selection_reply = on_message(priority=9, block=True, rule=Rule(_is_selection_reply))


def _record_nodes(record: Dict[str, Any], self_id: int) -> List[Dict[str, Any]]:
    """一条撤回记录对应的转发节点；正文保持原样，元数据交给节点本身显示。"""
    name = str(record["sender_name"] or "撤回记录")
    nodes = [
        make_node(
            decode_message(record["content"], MEDIA_DIR),
            name,
            record["user_id"] or self_id,
            timestamp=record["sent_at"],
        )
    ]
    # 原消息里的合并转发展开成独立节点，保住每条的发送人和原始时间。
    nodes.extend(decode_forward_nodes(record["content"], MEDIA_DIR, self_id))
    return nodes


def _pack_node_bundles(
    bundles: Sequence[Sequence[Dict[str, Any]]],
) -> List[List[List[Dict[str, Any]]]]:
    """按 OneBot 节点上限装箱，同时尽量不拆开同一条撤回记录。"""
    packs: List[List[List[Dict[str, Any]]]] = []
    current: List[List[Dict[str, Any]]] = []
    current_size = 0

    for bundle in bundles:
        nodes = list(bundle)
        for offset in range(0, len(nodes), MAX_FORWARD_NODES):
            chunk = nodes[offset:offset + MAX_FORWARD_NODES]
            if current and current_size + len(chunk) > MAX_FORWARD_NODES:
                packs.append(current)
                current = []
                current_size = 0
            current.append(chunk)
            current_size += len(chunk)

    if current:
        packs.append(current)
    return packs


async def _send_forward_once(
    bot: Bot,
    user_id: int,
    nodes: Sequence[Dict[str, Any]],
    source: str,
) -> bool:
    """发送一张转发卡片；扩展卡片标题不兼容时自动改用标准参数重试。"""
    payload = {
        "user_id": int(user_id),
        "messages": list(nodes),
        "source": source,
    }
    try:
        await bot.call_api("send_private_forward_msg", **payload)
        return True
    except Exception:
        payload.pop("source")
        try:
            await bot.call_api("send_private_forward_msg", **payload)
            return True
        except Exception as exc:
            logger.debug("[AntiRecall] 私聊 {} 的合并转发批次失败: {}", user_id, exc)
            return False


def _node_with_content(node: Dict[str, Any], content: Message) -> Dict[str, Any]:
    data = dict(node.get("data") or {})
    data["content"] = content
    return {"type": "node", "data": data}


def _failed_segment_label(message: Message) -> str:
    segment_type = message[0].type if message else ""
    return {
        "image": "[图片发送失败]",
        "face": "[表情发送失败]",
        "record": "[语音发送失败]",
        "video": "[视频发送失败]",
        "file": "[文件发送失败]",
        "text": "[文本发送失败]",
    }.get(segment_type, "[消息内容发送失败]")


async def _send_direct_part(
    bot: Bot,
    user_id: int,
    node: Dict[str, Any],
    content: Message,
) -> bool:
    """转发接口整体不可用时，直接发送这一小段，仍优先保住富媒体。"""
    data = node.get("data") or {}
    name = str(data.get("name") or "撤回记录")
    message = Message(MessageSegment.text(f"{name}（撤回记录）\n"))
    message += content
    try:
        await bot.send_private_msg(user_id=int(user_id), message=message)
        return True
    except Exception:
        try:
            await bot.send_private_msg(
                user_id=int(user_id),
                message=f"{name}（撤回记录）\n{_failed_segment_label(content)}",
            )
            return True
        except Exception as exc:
            logger.warning("[AntiRecall] 私聊 {} 的撤回消息段发送失败: {}", user_id, exc)
            return False


async def _salvage_node(
    bot: Bot,
    user_id: int,
    node: Dict[str, Any],
    source: str,
) -> bool:
    """二分节点内容；只有真正发不出的单个消息段才降级为占位文本。"""
    try:
        content = Message((node.get("data") or {}).get("content") or "")
    except Exception:
        content = Message()
    if not content:
        content = Message(MessageSegment.text("[空消息]"))

    async def send_part(part: Message) -> bool:
        if await _send_forward_once(bot, user_id, [_node_with_content(node, part)], source):
            return True
        if len(part) > 1:
            midpoint = len(part) // 2
            left_ok = await send_part(Message(part[:midpoint]))
            right_ok = await send_part(Message(part[midpoint:]))
            return left_ok and right_ok
        return await _send_direct_part(bot, user_id, node, part)

    if len(content) == 1:
        return await _send_direct_part(bot, user_id, node, content)
    midpoint = len(content) // 2
    left_ok = await send_part(Message(content[:midpoint]))
    right_ok = await send_part(Message(content[midpoint:]))
    return left_ok and right_ok


async def _send_bundle_group(
    bot: Bot,
    user_id: int,
    bundles: Sequence[Sequence[Dict[str, Any]]],
    source: str,
) -> bool:
    nodes = [node for bundle in bundles for node in bundle]
    if await _send_forward_once(bot, user_id, nodes, source):
        return True

    if len(bundles) > 1:
        midpoint = len(bundles) // 2
        left_ok = await _send_bundle_group(bot, user_id, bundles[:midpoint], source)
        right_ok = await _send_bundle_group(bot, user_id, bundles[midpoint:], source)
        return left_ok and right_ok

    node_bundle = list(bundles[0])
    all_ok = True
    for node in node_bundle:
        if len(node_bundle) > 1 and await _send_forward_once(bot, user_id, [node], source):
            continue
        if not await _salvage_node(bot, user_id, node, source):
            all_ok = False
    return all_ok


async def _send_records_resilient(
    bot: Bot,
    user_id: int,
    bundles: Sequence[Sequence[Dict[str, Any]]],
    source: str,
) -> bool:
    all_ok = True
    for pack in _pack_node_bundles(bundles):
        if not await _send_bundle_group(bot, user_id, pack, source):
            all_ok = False
    return all_ok


async def _resolve_group_names(bot: Bot, group_ids: Set[int]) -> Dict[int, str]:
    names: Dict[int, str] = {}
    for group_id in group_ids:
        try:
            info = await bot.get_group_info(group_id=int(group_id))
            names[group_id] = str(info.get("group_name") or group_id)
        except Exception:
            names[group_id] = str(group_id)
    return names


async def _send_group_records(
    bot: Bot,
    event: PrivateMessageEvent,
    group_id: int,
    limit: int,
) -> None:
    records = store.list_recalls(group_ids=[group_id], limit=limit)
    if not records:
        await bot.send_private_msg(user_id=event.user_id, message=f"群 {group_id} 最近没有撤回记录。")
        return

    group_names = await _resolve_group_names(bot, {group_id})
    group_label = group_names.get(group_id, str(group_id))
    bundles = [_record_nodes(record, event.self_id) for record in records]
    delivered = await _send_records_resilient(
        bot,
        event.user_id,
        bundles,
        source=f"{group_label}的撤回记录",
    )
    if not delivered:
        try:
            await bot.send_private_msg(
                user_id=event.user_id,
                message="部分撤回内容发送失败；其余可发送的图文已保留。",
            )
        except Exception:
            pass


async def _send_group_menu(
    bot: Bot,
    event: PrivateMessageEvent,
    stats: Sequence[Dict[str, int]],
) -> None:
    group_ids = [item["group_id"] for item in stats]
    group_names = await _resolve_group_names(bot, set(group_ids))
    lines = ["可查看的撤回记录："]
    for index, item in enumerate(stats, start=1):
        group_id = item["group_id"]
        lines.append(
            f"{index}. {group_names.get(group_id, group_id)}（{group_id}）"
            f" · {item['count']} 条"
        )
    lines.extend(["", f"回复 1–{len(group_ids)} 选择；回复“取消”退出。"])

    _pending_group_selections[_selection_key(event)] = (
        time.monotonic() + SELECTION_TTL,
        group_ids,
    )
    await bot.send_private_msg(user_id=event.user_id, message="\n".join(lines))


@selection_reply.handle()
async def handle_selection_reply(bot: Bot, event: PrivateMessageEvent):
    group_ids = _get_pending_selection(event)
    if group_ids is None:
        return

    text = event.get_plaintext().strip().lower()
    if text in _SELECTION_CANCEL_WORDS:
        _pending_group_selections.pop(_selection_key(event), None)
        await selection_reply.finish("已取消查看撤回记录。")

    choice = int(text)
    if not 1 <= choice <= len(group_ids):
        await selection_reply.finish(f"请输入 1–{len(group_ids)}，或回复“取消”。")

    _pending_group_selections.pop(_selection_key(event), None)
    await _send_group_records(
        bot,
        event,
        group_ids[choice - 1],
        store.get_config()["max_query_results"],
    )
    await selection_reply.finish()


@query_command.handle()
async def handle_query(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """私聊按群查询最近撤回的消息；群内误触保持静默。"""
    if isinstance(event, GroupMessageEvent):
        await query_command.finish()
    if not isinstance(event, PrivateMessageEvent):
        return

    raw_args = args.extract_plain_text().strip().split()
    config = store.get_config()
    limit = config["max_query_results"]
    allow_all = await is_superuser(bot, event)

    if not raw_args:
        stats = await _visible_group_stats(bot, event.user_id, allow_all)
        if not stats:
            await query_command.finish(
                "没有找到你可以查看的撤回记录。\n"
                "可能是：你所在的群还没开启反撤回，或者最近没有人撤回消息。"
            )
        if len(stats) == 1:
            await _send_group_records(bot, event, stats[0]["group_id"], limit)
        else:
            await _send_group_menu(bot, event, stats)
        await query_command.finish()

    if len(raw_args) > 2 or any(not token.isdigit() for token in raw_args):
        await query_command.finish("用法：/撤回 <群号> [条数]")

    selector = int(raw_args[0])
    target_group: Optional[int] = None
    if selector >= 10000:
        target_group = selector
    else:
        pending = _get_pending_selection(event)
        if pending is not None and 1 <= selector <= len(pending):
            target_group = pending[selector - 1]

    if target_group is None:
        await query_command.finish("请先发送 /撤回 选择群，或使用 /撤回 <群号> [条数]。")

    if len(raw_args) == 2:
        limit = max(1, min(config["max_query_results"], int(raw_args[1])))
    if not allow_all and not await _is_group_member(bot, event.user_id, target_group):
        await query_command.finish(f"你不在群 {target_group} 里，无法查看该群的撤回记录。")

    _pending_group_selections.pop(_selection_key(event), None)
    await _send_group_records(bot, event, target_group, limit)
    await query_command.finish()


# ==============================================================================
# 定期清理
# ==============================================================================

@scheduler.scheduled_job("cron", hour=4, minute=17, id="anti_recall_cleanup", max_instances=1, coalesce=True)
async def cleanup_job() -> None:
    try:
        stats = store.cleanup()
    except Exception as exc:
        logger.error("[AntiRecall] 清理失败: {}", exc)
        return

    if any(stats.values()):
        logger.info(
            "[AntiRecall] 清理完成：缓存 {}、记录 {}、媒体 {}",
            stats["cached_removed"], stats["recalls_removed"], stats["media_removed"],
        )
