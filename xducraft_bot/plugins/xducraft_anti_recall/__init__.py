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

    /撤回               最近的撤回消息（合并转发）
    /撤回 <群号>        指定群
    /撤回 <条数>        指定条数
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from nonebot import on_command, on_message, on_notice, require
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, GroupRecallNoticeEvent, Message, MessageEvent, PrivateMessageEvent,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.onebot import make_node, send_private_forward
from xducraft_bot.shared.permissions import can_manage, is_superuser

from .data_manager import MEDIA_DIR, store
from .message_codec import (
    decode_forward_nodes, decode_message, download_media, encode_message, summarize_content,
)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_anti_recall",
    description="记录群消息撤回，支持图片/表情包/合并转发，私聊查询",
    usage="群内：/反撤回 on|off|status|clear\n私聊：/撤回 [群号|条数]",
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


@recall_listener.handle()
async def handle_recall(bot: Bot, event: GroupRecallNoticeEvent):
    """收到撤回通知：固化记录，并趁 URL 还没失效把图片抓下来。"""
    if not feature_gate.is_enabled(FEATURE_KEY, event.group_id):
        return

    cached = store.take_cached_message(event.group_id, event.message_id)
    if cached is None:
        # 机器人启动前发的消息不在缓存里，这是正常情况。
        logger.debug("[AntiRecall] 群 {} 的消息 {} 不在缓存中。", event.group_id, event.message_id)
        return

    if store.is_user_exempt(cached["user_id"]):
        return

    created = store.record_recall(
        group_id=event.group_id,
        message_id=event.message_id,
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
            store.update_recall_content(event.group_id, event.message_id, cached["content"])
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


async def _visible_groups(bot: Bot, user_id: int, allow_all: bool) -> List[int]:
    """该用户能查看哪些群的撤回记录。"""
    candidates = store.list_recent_recall_groups(limit=30)
    if allow_all:
        return candidates

    visible = []
    for group_id in candidates:
        if await _is_group_member(bot, user_id, group_id):
            visible.append(group_id)
    return visible


def _format_time(timestamp: int) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "未知时间"


@query_command.handle()
async def handle_query(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """私聊查询最近撤回的消息。"""
    if isinstance(event, GroupMessageEvent):
        # 在群里被问到时给一句引导就好，不在群里贴内容。
        await query_command.finish("请私聊我发送 /撤回 查看撤回记录，群里不展示。")

    if not isinstance(event, PrivateMessageEvent):
        return

    raw_args = args.extract_plain_text().strip().split()
    config = store.get_config()
    limit = config["max_query_results"]
    target_group: Optional[int] = None

    for token in raw_args:
        if not token.isdigit():
            continue
        value = int(token)
        # 群号是 5 位以上，条数是小数字，靠位数区分足够可靠。
        if value >= 10000:
            target_group = value
        else:
            limit = max(1, min(config["max_query_results"], value))

    allow_all = await is_superuser(bot, event)

    if target_group is not None:
        if not allow_all and not await _is_group_member(bot, event.user_id, target_group):
            await query_command.finish(f"你不在群 {target_group} 里，无法查看该群的撤回记录。")
        group_ids: List[int] = [target_group]
    else:
        group_ids = await _visible_groups(bot, event.user_id, allow_all)
        if not group_ids:
            await query_command.finish(
                "没有找到你可以查看的撤回记录。\n"
                "可能是：你所在的群还没开启反撤回，或者最近没有人撤回消息。"
            )

    records = store.list_recalls(group_ids=group_ids, limit=limit)
    if not records:
        await query_command.finish("最近没有撤回记录。")

    group_names = await _resolve_group_names(bot, {record["group_id"] for record in records})

    nodes = []
    for record in records:
        group_label = group_names.get(record["group_id"], str(record["group_id"]))
        header = (
            f"【{group_label}】{record['sender_name']}({record['user_id']})\n"
            f"发送 {_format_time(record['sent_at'])} · 撤回 {_format_time(record['recalled_at'])}"
        )
        if record["operator_id"] and record["operator_id"] != record["user_id"]:
            header += f" · 由 {record['operator_id']} 操作"

        body = decode_message(record["content"], MEDIA_DIR)
        nodes.append(make_node(
            Message(header + "\n————————\n") + body,
            record["sender_name"] or "撤回记录",
            record["user_id"] or event.self_id,
        ))

        # 原消息里的合并转发展开成独立节点，保住每条的原始发送人。
        nodes.extend(decode_forward_nodes(record["content"], MEDIA_DIR, event.self_id))

    if not await send_private_forward(bot, event.user_id, nodes):
        # 合并转发被风控时退化成纯文本摘要，至少让用户知道撤了什么。
        summary = "\n".join(
            f"{_format_time(record['recalled_at'])} {record['sender_name']}: "
            f"{summarize_content(record['content'])}"
            for record in records
        )
        await query_command.finish(f"合并转发发送失败，以下是文字摘要：\n{summary}")

    await query_command.finish()


async def _resolve_group_names(bot: Bot, group_ids: Set[int]) -> Dict[int, str]:
    names: Dict[int, str] = {}
    for group_id in group_ids:
        try:
            info = await bot.get_group_info(group_id=int(group_id))
            names[group_id] = str(info.get("group_name") or group_id)
        except Exception:
            names[group_id] = str(group_id)
    return names


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
