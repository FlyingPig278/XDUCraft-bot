"""关键词与入群事件自动回复。

群级配置默认在私聊中完成，避免管理操作和回复录制刷屏。群管理员先发送
``/关键词 <群号>`` 查看状态与完整操作菜单；不知道群号时，可以在目标群只发送
一次 ``/关键词``，机器人会把该群的专用菜单私聊给管理员。

常用指令::

    /关键词 <群号>                         查看状态与菜单
    /关键词 <群号> on|off                  开关该群全部自动回复
    /关键词 <群号> add <词> [回复]           添加关键词
    /关键词 <群号> del|show <词>             删除或查看关键词
    /关键词 <群号> mode <词> <匹配方式>       包含 / 完全 / 开头 / 正则
    /关键词 <群号> join set|show|clear       配置入群欢迎
    /关键词 <群号> cooldown <秒>             设置默认冷却
    /关键词 global add|del ...              全局规则（限 SUPERUSER）
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Dict, List, Optional, Sequence, Tuple

import httpx
from nonebot import on_command, on_message, on_notice
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.typing import T_State

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.onebot import notify_privately, send_text_sections
from xducraft_bot.shared.permissions import can_manage_group, is_superuser

from . import data_manager as dm

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_keyword",
    description="可配置的关键词与入群事件自动回复",
    usage="私聊 /关键词 <群号> — 查看与管理该群自动回复",
)

FEATURE_KEY = "keyword_reply"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="关键词回复",
    description="匹配关键词或有新成员入群时自动回复",
    default_enabled=False,
    passive=True,
))

MEDIA_DOWNLOAD_TIMEOUT = 20.0
MAX_MEDIA_BYTES = 10 * 1024 * 1024

keyword_listener = on_message(
    priority=97, block=False,
    rule=Rule(lambda event: isinstance(event, GroupMessageEvent)),
)
join_listener = on_notice(
    priority=97, block=False,
    rule=Rule(lambda event: isinstance(event, GroupIncreaseNoticeEvent)),
)
keyword_command = on_command("关键词", aliases={"kw", "keyword"}, priority=10, block=True)

#: (group_id, rule_id) -> 上次触发时间
_cooldown: Dict[Tuple[int, str], float] = {}


def _on_cooldown(group_id: int, rule: Dict) -> bool:
    """检查并占用冷却窗口。"""
    seconds = rule.get("cooldown") or dm.get_default_cooldown(group_id)
    if seconds <= 0:
        return False

    key = (int(group_id), str(rule.get("id", "")))
    now = time.monotonic()
    last = _cooldown.get(key)
    if last is not None and now - last < seconds:
        return True

    _cooldown[key] = now
    if len(_cooldown) > 4096:
        # 简单粗暴地清一半最旧的，防止无限增长。
        for stale, _ in sorted(_cooldown.items(), key=lambda item: item[1])[:2048]:
            _cooldown.pop(stale, None)
    return False


def _plain_text(message: Message) -> str:
    return "".join(
        str(segment.data.get("text", "")) for segment in message if segment.type == "text"
    ).strip()


async def _send_saved_replies(
    bot: Bot,
    event,
    replies: Sequence[str],
    *,
    at_user_id: Optional[int] = None,
) -> None:
    """按顺序发送已保存的消息；入群欢迎的首条消息会提及新成员。"""
    for index, reply in enumerate(replies):
        message = Message()
        if index == 0 and at_user_id is not None:
            message += MessageSegment.at(at_user_id)
            message += MessageSegment.text(" ")
        message += Message(_restore_reply(reply))
        await bot.send(event, message)


# ==============================================================================
# 触发
# ==============================================================================

@keyword_listener.handle()
async def handle_keyword(bot: Bot, event: GroupMessageEvent):
    if not feature_gate.is_enabled(FEATURE_KEY, event.group_id):
        return

    text = _plain_text(event.message)
    if not text or text.startswith("/"):
        # 指令交给对应插件处理，不要被关键词抢走。
        return

    rule = dm.match_rules(text, event.group_id)
    if rule is None or _on_cooldown(event.group_id, rule):
        return

    try:
        await _send_saved_replies(bot, event, rule["replies"])
    except Exception as exc:
        logger.warning("[Keyword] 群 {} 发送关键词回复失败: {}", event.group_id, exc)


@join_listener.handle()
async def handle_member_join(bot: Bot, event: GroupIncreaseNoticeEvent):
    if str(event.user_id) == str(bot.self_id):
        return
    if not feature_gate.is_enabled(FEATURE_KEY, event.group_id):
        return

    replies = dm.get_join_replies(event.group_id)
    if not replies:
        return

    try:
        await _send_saved_replies(bot, event, replies, at_user_id=event.user_id)
    except Exception as exc:
        logger.warning("[Keyword] 群 {} 发送入群欢迎失败: {}", event.group_id, exc)


def _restore_reply(reply: str) -> str:
    """把存的本地文件名还原成可发送的 ``file:///`` 地址。"""
    def replace(match: re.Match) -> str:
        name = match.group(1)
        path = dm.media_path(name)
        if os.path.exists(path):
            return f"[CQ:image,file=file:///{path}]"
        return "[图片已失效]"

    return re.sub(r"\[CQ:image,file=kwlocal://([^\]]+)\]", replace, reply)


# ==============================================================================
# 配置
# ==============================================================================

async def _persist_reply_media(message: Message) -> str:
    """把回复消息序列化成 CQ 串，其中的图片下载到本地。

    预设回复是长期使用的，直接存 QQ 的临时 URL 过几天就会变成裂图。
    """
    parts: List[str] = []
    downloads: List[Tuple[int, str]] = []

    for segment in message:
        if segment.type == "reply":
            # 用户常会“回复”录制提示；旧消息引用不能作为长期回复重放。
            continue
        if segment.type == "image":
            url = str(segment.data.get("url") or segment.data.get("file") or "")
            if url.startswith(("http://", "https://")):
                downloads.append((len(parts), url))
                parts.append("")  # 占位，下载完再填
                continue
        parts.append(str(segment))

    if downloads:
        os.makedirs(dm.MEDIA_DIR, exist_ok=True)

        async with httpx.AsyncClient(timeout=MEDIA_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            async def fetch(index: int, url: str) -> None:
                try:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > MAX_MEDIA_BYTES:
                                parts[index] = "[图片过大未保存]"
                                return
                    import hashlib

                    name = hashlib.sha256(url.encode()).hexdigest()[:32] + ".img"
                    with open(dm.media_path(name), "wb") as handle:
                        handle.write(bytes(chunks))
                    parts[index] = f"[CQ:image,file=kwlocal://{name}]"
                except Exception as exc:
                    logger.debug("[Keyword] 下载回复图片失败: {}", exc)
                    parts[index] = "[图片保存失败]"

            await asyncio.gather(*(fetch(index, url) for index, url in downloads), return_exceptions=True)

    return "".join(parts)


def _describe_rule(rule: Dict, index: Optional[int] = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    state = "" if rule.get("enabled", True) else "（已停用）"
    scope = {"group": "本群", "global": "全局"}.get(rule.get("scope", ""), "")
    scope_text = f"[{scope}] " if scope else ""
    keywords = " / ".join(rule["keywords"])
    mode = dm.MATCH_LABELS.get(rule["match"], rule["match"])
    previews = [
        re.sub(r"\[CQ:[^\]]+\]", "[富文本]", reply).replace("\n", " ")
        for reply in rule["replies"]
    ]
    preview = " | ".join(previews)
    if len(preview) > 40:
        preview = preview[:40] + "…"
    count = f"，{len(previews)} 条消息" if len(previews) > 1 else ""
    return f"{prefix}{scope_text}{keywords}（{mode}{count}）{state}\n   → {preview}"


_CAPTURE_STATE_KEY = "_keyword_reply_capture"


async def _start_capture(
    state: T_State,
    *,
    kind: str,
    group_id: Optional[int],
    keyword: Optional[str] = None,
) -> None:
    state[_CAPTURE_STATE_KEY] = {
        "kind": kind,
        "group_id": group_id,
        "keyword": keyword,
        "replies": [],
    }
    scope = "全局" if group_id is None else f"群 {group_id}"
    target = f"{scope}关键词「{keyword}」" if kind == "rule" else f"{scope}入群欢迎"
    await keyword_command.pause(
        f"开始录制{target}的回复。\n"
        "现在请直接发送第 1 条回复。文字、图片、表情、@ 可以混排；"
        f"最多 {dm.MAX_REPLIES_PER_TRIGGER} 条。\n"
        "每发一条我都会确认；全部发完后单独发送“完成”，"
        "不想保存则发送“取消”。"
    )


def _private_entry_help() -> str:
    return (
        "自动回复配置入口\n"
        "所有设置和回复录制都能在当前私聊完成，不会把配置内容发到群里。\n\n"
        "请发送：/关键词 <群号>\n"
        "例如：/关键词 123456789\n\n"
        "不知道群号时，只需在目标群发送一次 /关键词；"
        "我会把该群的专用菜单私聊给你，群里不会显示菜单。\n"
        "SUPERUSER 管理全局规则可发送：/关键词 global list"
    )


def _group_command_help(group_id: int) -> str:
    prefix = f"/关键词 {group_id}"
    return (
        f"群 {group_id} 的私聊配置菜单\n"
        "推荐首次按这个顺序操作：\n"
        f"1. {prefix} on\n"
        f"2. {prefix} add 新手教程\n"
        "   收到录制提示后逐条发送回复，最后单独发送“完成”。\n"
        f"3. {prefix} join set\n"
        "   按同样方式录制入群欢迎；首条发送时会自动 @ 新成员。\n\n"
        "其他操作：\n"
        f"{prefix} show <关键词>       查看完整回复\n"
        f"{prefix} mode <关键词> 完全  改为完全匹配\n"
        f"{prefix} del <关键词>        删除关键词\n"
        f"{prefix} join show          查看入群欢迎\n"
        f"{prefix} join clear         清除入群欢迎\n"
        f"{prefix} cooldown <秒>       设置关键词冷却\n"
        f"{prefix} off                关闭该群全部自动回复\n"
        f"{prefix}                    重新查看状态和菜单"
    )


async def _redirect_group_configuration(bot: Bot, event: GroupMessageEvent) -> None:
    group_id = int(event.group_id)
    if not await can_manage_group(bot, event, group_id):
        await keyword_command.finish("只有群管理员可以配置自动回复。")

    sent = await notify_privately(
        bot,
        event.user_id,
        "为避免在大群刷屏，群内的配置命令不会执行；请在本私聊中操作。\n\n"
        + _group_command_help(group_id),
    )
    if sent:
        await keyword_command.finish()
    await keyword_command.finish(
        "无法向你发送私聊。请先添加机器人好友，然后再次发送 /关键词。"
    )


@keyword_command.handle()
async def handle_command(
    bot: Bot,
    event: MessageEvent,
    state: T_State,
    args: Message = CommandArg(),
):
    if isinstance(event, GroupMessageEvent):
        await _redirect_group_configuration(bot, event)
        return

    head, _ = _split_message_head(args, 1)
    if not head:
        await keyword_command.finish(_private_entry_help())

    if head[0].lower() == "global":
        await _handle_global(bot, event, args, state)
        return

    try:
        group_id = int(head[0])
    except ValueError:
        await keyword_command.finish(
            "未识别目标群号。\n\n" + _private_entry_help()
        )
    if group_id <= 0:
        await keyword_command.finish("群号必须是正整数。\n\n" + _private_entry_help())

    if not await can_manage_group(bot, event, group_id):
        await keyword_command.finish(
            f"无法确认你是群 {group_id} 的群主或管理员。\n"
            "请检查群号和管理员身份；SUPERUSER 不受此限制。"
        )

    _, scoped_args = _split_message_head(args, 1)
    await _handle_group_command(
        bot,
        event,
        state,
        scoped_args or Message(),
        group_id,
    )


async def _handle_group_command(
    bot: Bot,
    event: MessageEvent,
    state: T_State,
    args: Message,
    group_id: int,
) -> None:
    raw_args = args.extract_plain_text().strip().split(maxsplit=2)
    action = raw_args[0].lower() if raw_args else "list"
    prefix = f"/关键词 {group_id}"

    if action in {"list", "列表", "help", "帮助", ""} and len(raw_args) <= 1:
        await _show_list(bot, event, group_id)
        return

    if action in {"on", "开", "开启"}:
        changed = feature_gate.set_enabled(FEATURE_KEY, group_id, True)
        await keyword_command.finish(
            f"已开启群 {group_id} 的自动回复。"
            if changed else
            f"群 {group_id} 的自动回复已经是开启状态。"
        )

    if action in {"off", "关", "关闭"}:
        changed = feature_gate.set_enabled(FEATURE_KEY, group_id, False)
        await keyword_command.finish(
            f"已关闭群 {group_id} 的自动回复。"
            if changed else
            f"群 {group_id} 的自动回复已经是关闭状态。"
        )

    if action in {"join", "welcome", "入群", "欢迎"}:
        await _handle_join(bot, event, args, state, group_id)
        return

    if action in {"add", "添加"}:
        if len(raw_args) < 2:
            await keyword_command.finish(
                f"缺少关键词。请发送：{prefix} add <关键词>\n"
                f"例如：{prefix} add 新手教程\n"
                "随后我会等待你逐条发送回复内容。"
            )
        keyword = raw_args[1]
        if dm.find_rule(keyword, group_id=group_id) is not None:
            await keyword_command.finish(
                f"群 {group_id} 已有关键词「{keyword}」。\n"
                f"查看：{prefix} show {keyword}\n"
                f"重做时请先删除：{prefix} del {keyword}"
            )

        _, reply_message = _split_message_head(args, 2)
        if reply_message is None:
            await _start_capture(
                state,
                kind="rule",
                group_id=group_id,
                keyword=keyword,
            )

        reply = await _persist_reply_media(reply_message)
        rule = dm.add_rule(keyword, [reply], group_id=group_id)
        if rule is None:
            await keyword_command.finish(
                f"添加失败：关键词「{keyword}」的回复为空、过长，或规则数量已达上限。"
            )

        await keyword_command.finish(
            f"已添加群 {group_id} 的关键词「{keyword}」"
            f"（{dm.MATCH_LABELS[rule['match']]}）。\n"
            f"改为完全匹配：{prefix} mode {keyword} 完全"
        )

    if action in {"del", "delete", "remove", "删除"}:
        if len(raw_args) < 2:
            await keyword_command.finish(f"缺少关键词。请发送：{prefix} del <关键词>")
        keyword = raw_args[1]
        if dm.remove_rule(keyword, group_id=group_id):
            await keyword_command.finish(f"已删除群 {group_id} 的关键词「{keyword}」。")
        await keyword_command.finish(
            f"群 {group_id} 没有找到关键词「{keyword}」。\n"
            f"发送 {prefix} 查看已有规则。"
        )

    if action in {"show", "查看"}:
        if len(raw_args) < 2:
            await keyword_command.finish(f"缺少关键词。请发送：{prefix} show <关键词>")
        rule = dm.find_rule(raw_args[1], group_id=group_id) or dm.find_rule(raw_args[1], group_id=None)
        if rule is None:
            await keyword_command.finish(f"没有找到关键词「{raw_args[1]}」。")
        await keyword_command.send(
            f"关键词「{' / '.join(rule['keywords'])}」的回复内容（{len(rule['replies'])} 条）："
        )
        await _send_saved_replies(bot, event, rule["replies"])
        await keyword_command.finish()

    if action in {"mode", "匹配"}:
        if len(raw_args) < 3:
            await keyword_command.finish(
                f"参数不完整。请发送：{prefix} mode <关键词> <包含|完全|开头|正则>\n"
                f"例如：{prefix} mode 新手教程 完全"
            )
        keyword, mode_text = raw_args[1], raw_args[2].strip().lower()
        mode = _parse_match_mode(mode_text)
        if mode is None:
            await keyword_command.finish("匹配方式只能是：包含 / 完全 / 开头 / 正则")
        if mode == dm.MATCH_REGEX and not dm.is_valid_regex(keyword):
            await keyword_command.finish(f"「{keyword}」不是合法的正则表达式。")
        if dm.update_rule(keyword, group_id, match=mode):
            await keyword_command.finish(
                f"已将群 {group_id} 的「{keyword}」改为{dm.MATCH_LABELS[mode]}。"
            )
        await keyword_command.finish(f"群 {group_id} 没有找到关键词「{keyword}」。")

    if action in {"cooldown", "冷却"}:
        if len(raw_args) < 2 or not raw_args[1].isdigit():
            await keyword_command.finish(
                f"请发送：{prefix} cooldown <秒>\n"
                f"群 {group_id} 当前默认冷却：{dm.get_default_cooldown(group_id)} 秒"
            )
        dm.set_default_cooldown(int(raw_args[1]), group_id=group_id)
        await keyword_command.finish(
            f"已将群 {group_id} 的关键词默认冷却设为 "
            f"{dm.get_default_cooldown(group_id)} 秒。"
        )

    await keyword_command.finish(
        f"没有识别操作「{action}」。\n\n" + _group_command_help(group_id)
    )


def _parse_match_mode(text: str) -> Optional[str]:
    mapping = {
        "包含": dm.MATCH_CONTAINS, "contains": dm.MATCH_CONTAINS,
        "完全": dm.MATCH_EXACT, "精确": dm.MATCH_EXACT, "exact": dm.MATCH_EXACT,
        "开头": dm.MATCH_PREFIX, "前缀": dm.MATCH_PREFIX, "prefix": dm.MATCH_PREFIX,
        "正则": dm.MATCH_REGEX, "regex": dm.MATCH_REGEX,
    }
    return mapping.get(text)


def _split_message_head(
    message: Message,
    word_count: int,
) -> Tuple[List[str], Optional[Message]]:
    """取出开头的若干纯文本单词，同时完整保留后面的富文本消息段。"""
    words: List[str] = []
    remaining = Message()

    for segment in message:
        if len(words) >= word_count:
            remaining += segment
            continue
        if segment.type != "text":
            continue

        text = str(segment.data.get("text", ""))
        position = 0
        while len(words) < word_count:
            match = re.search(r"\S+", text[position:])
            if match is None:
                position = len(text)
                break
            start = position + match.start()
            end = position + match.end()
            words.append(text[start:end])
            position = end

        if len(words) >= word_count:
            tail = text[position:].lstrip()
            if tail:
                remaining += MessageSegment.text(tail)

    return words, remaining if remaining else None


def _control_message_text(message: Message) -> Optional[str]:
    if any(segment.type not in {"text", "reply"} for segment in message):
        return None
    return _plain_text(message)


async def _finish_capture(state: T_State) -> None:
    capture = state.pop(_CAPTURE_STATE_KEY, None)
    if not isinstance(capture, dict):
        await keyword_command.finish("录制状态已失效，请重新执行配置命令。")

    replies = capture.get("replies", [])
    if capture.get("kind") == "rule":
        keyword = str(capture.get("keyword") or "")
        group_id = capture.get("group_id")
        rule = dm.add_rule(keyword, replies, group_id=group_id)
        if rule is None:
            await keyword_command.finish(
                f"保存失败：关键词「{keyword}」已存在，回复不合法，或规则数量已达上限。"
            )
        if group_id is None:
            await keyword_command.finish(
                f"已保存全局关键词「{keyword}」的 {len(replies)} 条回复。\n"
                "查看规则：/关键词 global list"
            )
        await keyword_command.finish(
            f"已保存群 {group_id} 关键词「{keyword}」的 {len(replies)} 条回复。\n"
            f"查看内容：/关键词 {group_id} show {keyword}"
        )

    group_id = capture.get("group_id")
    if group_id is None:
        await keyword_command.finish("录制状态已失效，请重新配置入群欢迎。")
    changed = dm.set_join_replies(int(group_id), replies)
    if not changed and dm.get_join_replies(int(group_id)) != replies:
        await keyword_command.finish("入群欢迎保存失败：回复为空、过长或数量超限。")
    await keyword_command.finish(
        f"已保存群 {group_id} 的 {len(replies)} 条入群欢迎消息。\n"
        f"查看内容：/关键词 {group_id} join show"
    )


@keyword_command.receive("configured_reply")
async def receive_configured_reply(
    event: MessageEvent,
    state: T_State,
    matcher: Matcher,
) -> None:
    capture = state.get(_CAPTURE_STATE_KEY)
    if not isinstance(capture, dict):
        await matcher.finish("录制状态已失效，请重新执行配置命令。")

    message = event.get_message()
    control = _control_message_text(message)
    if control in {"取消", "/取消", "cancel", "/cancel"}:
        state.pop(_CAPTURE_STATE_KEY, None)
        await matcher.finish("已取消本次回复录制。")
    if control in {"完成", "/完成", "done", "/done", "保存"}:
        if not capture["replies"]:
            await matcher.reject_receive(
                "configured_reply",
                "还没有录制任何消息。请先发送回复内容，或发送“取消”。",
            )
        await _finish_capture(state)

    reply = await _persist_reply_media(message)
    if not reply:
        await matcher.reject_receive(
            "configured_reply",
            "这条消息没有可保存的内容，请重新发送；发送“取消”可退出。",
        )
    if len(reply) > dm.MAX_REPLY_LENGTH:
        await matcher.reject_receive(
            "configured_reply",
            f"这条消息超过 {dm.MAX_REPLY_LENGTH} 个字符，请缩短后重发。",
        )

    capture["replies"].append(reply)
    count = len(capture["replies"])
    if count >= dm.MAX_REPLIES_PER_TRIGGER:
        await _finish_capture(state)
    await matcher.reject_receive(
        "configured_reply",
        f"已记录第 {count} 条。可继续发送下一条；发送“完成”保存，发送“取消”放弃。",
    )


async def _handle_join(
    bot: Bot,
    event: MessageEvent,
    args: Message,
    state: T_State,
    group_id: int,
) -> None:
    tokens = args.extract_plain_text().strip().split(maxsplit=2)
    sub_action = tokens[1].lower() if len(tokens) > 1 else "show"
    prefix = f"/关键词 {group_id} join"

    if sub_action in {"show", "status", "查看", "状态", "list", "列表"}:
        replies = dm.get_join_replies(group_id)
        enabled, _ = feature_gate.resolve(FEATURE_KEY, group_id)
        if not replies:
            await keyword_command.finish(
                f"群 {group_id} 的自动回复当前{'开启' if enabled else '关闭'}，"
                "尚未配置入群欢迎。\n"
                f"发送 {prefix} set 开始录制。"
            )
        await keyword_command.send(
            f"群 {group_id} 的入群欢迎（{len(replies)} 条，自动回复当前"
            f"{'开启' if enabled else '关闭'}）："
        )
        await _send_saved_replies(bot, event, replies)
        await keyword_command.finish()

    if sub_action in {"set", "设置", "add", "添加"}:
        _, reply_message = _split_message_head(args, 2)
        if reply_message is None:
            await _start_capture(state, kind="join", group_id=group_id)
        reply = await _persist_reply_media(reply_message)
        if not reply or len(reply) > dm.MAX_REPLY_LENGTH:
            await keyword_command.finish("入群欢迎保存失败：回复为空或过长。")
        changed = dm.set_join_replies(group_id, [reply])
        if not changed and dm.get_join_replies(group_id) != [reply]:
            await keyword_command.finish("入群欢迎保存失败。")
        await keyword_command.finish(
            f"已保存群 {group_id} 的 1 条入群欢迎消息。\n"
            f"查看效果：{prefix} show"
        )

    if sub_action in {"clear", "del", "delete", "清除", "删除", "关闭"}:
        if dm.clear_join_replies(group_id):
            await keyword_command.finish(f"已清除群 {group_id} 的入群欢迎。")
        await keyword_command.finish(f"群 {group_id} 尚未配置入群欢迎。")

    await keyword_command.finish(
        "没有识别入群欢迎操作。请使用：\n"
        f"{prefix} set    开始录制\n"
        f"{prefix} show   查看\n"
        f"{prefix} clear  清除"
    )


async def _show_list(bot: Bot, event: MessageEvent, group_id: int) -> None:
    rules = dm.get_effective_rules(group_id)
    join_replies = dm.get_join_replies(group_id)
    enabled, _ = feature_gate.resolve(FEATURE_KEY, group_id)

    status = "\n".join([
        f"群 {group_id} 当前状态",
        f"自动回复总开关：{'开启' if enabled else '关闭'}",
        f"入群欢迎：{'已配置 ' + str(len(join_replies)) + ' 条' if join_replies else '未配置'}",
        f"关键词规则：{len(rules)} 条（含全局规则）",
        f"关键词默认冷却：{dm.get_default_cooldown(group_id)} 秒",
        "",
        _group_command_help(group_id),
    ])
    await keyword_command.send(status)

    if rules:
        body = [_describe_rule(rule, index + 1) for index, rule in enumerate(rules)]
        await send_text_sections(bot, event, ["\n".join(body)], title=f"群 {group_id} 自动回复规则")
    await keyword_command.finish()


async def _handle_global(
    bot: Bot,
    event: MessageEvent,
    args: Message,
    state: T_State,
) -> None:
    """全局规则管理，只有 SUPERUSER 能用。"""
    if not await is_superuser(bot, event):
        await keyword_command.finish("全局关键词只有超级用户可以配置。")

    tokens = args.extract_plain_text().strip().split(maxsplit=2)
    sub_action = tokens[1].lower() if len(tokens) > 1 else "list"

    if sub_action in {"list", "列表"}:
        rules = dm.get_global_rules()
        if not rules:
            await keyword_command.finish("还没有配置全局关键词。")
        body = "\n".join(_describe_rule(rule, index + 1) for index, rule in enumerate(rules))
        await keyword_command.finish(f"全局关键词（所有启用的群都生效）：\n{body}")

    if sub_action in {"add", "添加"}:
        head, reply_message = _split_message_head(args, 3)
        if len(head) < 3:
            await keyword_command.finish(
                "用法：/关键词 global add <关键词> [回复内容]\n"
                "省略回复内容后可单独录制图文或多条消息。"
            )
        keyword = head[2]
        if dm.find_rule(keyword, group_id=None) is not None:
            await keyword_command.finish(f"添加失败：全局关键词「{keyword}」已存在。")
        if reply_message is None:
            await _start_capture(
                state,
                kind="rule",
                group_id=None,
                keyword=keyword,
            )

        reply = await _persist_reply_media(reply_message)
        if dm.add_rule(keyword, [reply], group_id=None) is None:
            await keyword_command.finish(
                f"添加失败：全局关键词「{keyword}」的回复为空、过长，或规则数量已达上限。"
            )
        await keyword_command.finish(
            f"已添加全局关键词「{keyword}」，所有启用自动回复的群都会生效。"
        )

    if sub_action in {"del", "delete", "删除"}:
        if len(tokens) < 3:
            await keyword_command.finish("用法：/关键词 global del <关键词>")
        if dm.remove_rule(tokens[2], group_id=None):
            await keyword_command.finish(f"已删除全局关键词「{tokens[2]}」。")
        await keyword_command.finish(f"没有找到全局关键词「{tokens[2]}」。")

    await keyword_command.finish(
        "用法：\n"
        "/关键词 global list\n"
        "/关键词 global add <词> [回复]\n"
        "/关键词 global del <词>"
    )
