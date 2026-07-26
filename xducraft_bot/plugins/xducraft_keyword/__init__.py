"""关键词自动回复。

有人在群里发“新手教程”，机器人就把预设好的那段内容发出来。

三条设计约束（都来自实际会踩的坑）：

- **未启用的群完全不响应。** 监听器优先级低且 ``block=False``，
  开关关掉时连匹配都不做。
- **配置指令的回执默认走私聊。** 在几百人的大群里连着调十条关键词，
  每条都回一句就是刷屏。
- **每条规则有冷却时间。** 否则有人复读关键词，机器人就跟着复读。

指令::

    /关键词                      查看本群规则
    /关键词 add <词> <回复>       添加本群规则（回复可带图片/表情）
    /关键词 del <词>              删除
    /关键词 show <词>             查看某条规则的完整回复
    /关键词 mode <词> <匹配方式>   包含 / 完全 / 开头 / 正则
    /关键词 on|off                开关本群关键词回复
    /关键词 global add|del ...    全局规则（所有启用的群都生效，限 SUPERUSER）
    /关键词 cooldown <秒>         设置默认冷却
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx
from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, Message, MessageEvent, MessageSegment,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.onebot import reply_quietly, send_text_sections
from xducraft_bot.shared.permissions import can_manage, is_superuser

from . import data_manager as dm

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_keyword",
    description="可配置的关键词自动回复",
    usage="/关键词 — 查看与管理本群关键词回复",
)

FEATURE_KEY = "keyword_reply"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="关键词回复",
    description="匹配到预设关键词时自动回复",
    default_enabled=False,
    passive=True,
))

MEDIA_DOWNLOAD_TIMEOUT = 20.0
MAX_MEDIA_BYTES = 10 * 1024 * 1024

keyword_listener = on_message(
    priority=97, block=False,
    rule=Rule(lambda event: isinstance(event, GroupMessageEvent)),
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
        await bot.send(event, Message(_restore_reply(rule["reply"])))
    except Exception as exc:
        logger.warning("[Keyword] 群 {} 发送关键词回复失败: {}", event.group_id, exc)


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
    preview = re.sub(r"\[CQ:[^\]]+\]", "[图片]", rule["reply"]).replace("\n", " ")
    if len(preview) > 40:
        preview = preview[:40] + "…"
    return f"{prefix}{scope_text}{keywords}（{mode}）{state}\n   → {preview}"


@keyword_command.handle()
async def handle_command(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip().split(maxsplit=2)
    action = raw_args[0].lower() if raw_args else "list"

    group_id = getattr(event, "group_id", None)
    is_group = isinstance(event, GroupMessageEvent)

    # 全局规则只有 SUPERUSER 能动，且可以在私聊里配置。
    if action == "global":
        await _handle_global(bot, event, args)
        return

    if not is_group:
        await keyword_command.finish(
            "请在需要配置的群里使用 /关键词。\n"
            "配置全局规则（所有群生效）请发送 /关键词 global add <词> <回复>。"
        )

    if action in {"list", "列表", ""} and len(raw_args) <= 1:
        await _show_list(bot, event)
        return

    if not await can_manage(bot, event):
        await keyword_command.finish("只有群管理员可以配置关键词回复。")

    quiet = True  # 配置类回执一律尽量私聊，避免在大群里刷屏

    if action in {"on", "开", "开启"}:
        changed = feature_gate.set_enabled(FEATURE_KEY, group_id, True)
        await reply_quietly(
            bot,
            event,
            "已开启本群关键词回复。" if changed else "本群关键词回复已经是开启状态。",
            quiet=quiet,
        )
        await keyword_command.finish()

    if action in {"off", "关", "关闭"}:
        changed = feature_gate.set_enabled(FEATURE_KEY, group_id, False)
        await reply_quietly(
            bot,
            event,
            "已关闭本群关键词回复。" if changed else "本群关键词回复已经是关闭状态。",
            quiet=quiet,
        )
        await keyword_command.finish()

    if action in {"add", "添加"}:
        keyword, reply_message = _split_add_arguments(args)
        if not keyword or not reply_message:
            await keyword_command.finish(
                "用法：/关键词 add <关键词> <回复内容>\n"
                "回复内容可以包含图片和表情，会一并保存。"
            )
        reply = await _persist_reply_media(reply_message)
        rule = dm.add_rule(keyword, reply, group_id=group_id)
        if rule is None:
            await keyword_command.finish(f"添加失败：关键词「{keyword}」已存在，或规则数量已达上限。")

        await reply_quietly(
            bot, event,
            f"已添加关键词「{keyword}」（{dm.MATCH_LABELS[rule['match']]}）\n"
            f"现在群里有人发送包含它的消息就会自动回复。\n"
            f"可用 /关键词 mode {keyword} 完全 改成精确匹配。",
            quiet=quiet,
        )
        await keyword_command.finish()

    if action in {"del", "delete", "remove", "删除"}:
        if len(raw_args) < 2:
            await keyword_command.finish("用法：/关键词 del <关键词>")
        keyword = raw_args[1]
        if dm.remove_rule(keyword, group_id=group_id):
            await reply_quietly(bot, event, f"已删除关键词「{keyword}」。", quiet=quiet)
            await keyword_command.finish()
        await keyword_command.finish(f"本群没有找到关键词「{keyword}」。用 /关键词 查看已有规则。")

    if action in {"show", "查看"}:
        if len(raw_args) < 2:
            await keyword_command.finish("用法：/关键词 show <关键词>")
        rule = dm.find_rule(raw_args[1], group_id=group_id) or dm.find_rule(raw_args[1], group_id=None)
        if rule is None:
            await keyword_command.finish(f"没有找到关键词「{raw_args[1]}」。")
        await keyword_command.send(f"关键词「{' / '.join(rule['keywords'])}」的回复内容：")
        await keyword_command.finish(Message(_restore_reply(rule["reply"])))

    if action in {"mode", "匹配"}:
        if len(raw_args) < 3:
            await keyword_command.finish(
                "用法：/关键词 mode <关键词> <包含|完全|开头|正则>"
            )
        keyword, mode_text = raw_args[1], raw_args[2].strip().lower()
        mode = _parse_match_mode(mode_text)
        if mode is None:
            await keyword_command.finish("匹配方式只能是：包含 / 完全 / 开头 / 正则")
        if mode == dm.MATCH_REGEX and not dm.is_valid_regex(keyword):
            await keyword_command.finish(f"「{keyword}」不是合法的正则表达式。")
        if dm.update_rule(keyword, group_id, match=mode):
            await reply_quietly(bot, event, f"已将「{keyword}」的匹配方式改为{dm.MATCH_LABELS[mode]}。", quiet=quiet)
            await keyword_command.finish()
        await keyword_command.finish(f"本群没有找到关键词「{keyword}」。")

    if action in {"cooldown", "冷却"}:
        if len(raw_args) < 2 or not raw_args[1].isdigit():
            await keyword_command.finish(
                f"用法：/关键词 cooldown <秒>\n本群默认冷却：{dm.get_default_cooldown(group_id)} 秒"
            )
        dm.set_default_cooldown(int(raw_args[1]), group_id=group_id)
        await reply_quietly(
            bot,
            event,
            f"已将本群默认冷却设为 {dm.get_default_cooldown(group_id)} 秒。",
            quiet=quiet,
        )
        await keyword_command.finish()

    await keyword_command.finish(
        "用法：\n"
        "/关键词 — 查看本群规则\n"
        "/关键词 add <词> <回复> — 添加\n"
        "/关键词 del <词> — 删除\n"
        "/关键词 show <词> — 查看完整回复\n"
        "/关键词 mode <词> <包含|完全|开头|正则>\n"
        "/关键词 cooldown <秒>\n"
        "/关键词 on|off — 开关本群关键词回复"
    )


def _parse_match_mode(text: str) -> Optional[str]:
    mapping = {
        "包含": dm.MATCH_CONTAINS, "contains": dm.MATCH_CONTAINS,
        "完全": dm.MATCH_EXACT, "精确": dm.MATCH_EXACT, "exact": dm.MATCH_EXACT,
        "开头": dm.MATCH_PREFIX, "前缀": dm.MATCH_PREFIX, "prefix": dm.MATCH_PREFIX,
        "正则": dm.MATCH_REGEX, "regex": dm.MATCH_REGEX,
    }
    return mapping.get(text)


def _split_add_arguments(args: Message) -> Tuple[str, Optional[Message]]:
    """从 ``add <关键词> <回复...>`` 里拆出关键词和剩下的富文本回复。

    回复部分可能包含图片段，所以不能简单地对纯文本做 split——必须在
    ``Message`` 层面切，才能把图片保留下来。
    """
    remaining = Message()
    keyword = ""
    consumed_action = False

    for segment in args:
        if segment.type != "text":
            if keyword:
                remaining += segment
            continue

        text = str(segment.data.get("text", ""))
        if keyword:
            remaining += MessageSegment.text(text)
            continue

        tokens = text.split(maxsplit=2 if not consumed_action else 1)
        if not consumed_action:
            # tokens[0] 是 "add"
            if len(tokens) < 2:
                consumed_action = True
                continue
            keyword = tokens[1]
            consumed_action = True
            if len(tokens) >= 3:
                remaining += MessageSegment.text(tokens[2])
        else:
            if len(tokens) < 1:
                continue
            keyword = tokens[0]
            if len(tokens) >= 2:
                remaining += MessageSegment.text(tokens[1])

    if not remaining:
        return keyword, None
    return keyword, remaining


async def _show_list(bot: Bot, event: GroupMessageEvent) -> None:
    rules = dm.get_effective_rules(event.group_id)
    enabled, _ = feature_gate.resolve(FEATURE_KEY, event.group_id)

    header = [
        f"本群关键词回复：{'开启' if enabled else '关闭'}",
        f"本群默认冷却：{dm.get_default_cooldown(event.group_id)} 秒",
    ]
    if not rules:
        header.append("\n还没有配置任何关键词。管理员可用 /关键词 add <词> <回复> 添加。")
        await keyword_command.finish("\n".join(header))

    body = [_describe_rule(rule, index + 1) for index, rule in enumerate(rules)]
    await send_text_sections(bot, event, ["\n".join(header + [""] + body)], title="关键词回复")
    await keyword_command.finish()


async def _handle_global(bot: Bot, event: MessageEvent, args: Message) -> None:
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
        # 去掉前导的 "global"，复用群级的参数拆分逻辑。
        trimmed = Message()
        skipped = False
        for segment in args:
            if not skipped and segment.type == "text":
                text = str(segment.data.get("text", ""))
                parts = text.split(maxsplit=1)
                if parts and parts[0].lower() == "global":
                    skipped = True
                    if len(parts) > 1:
                        trimmed += MessageSegment.text(parts[1])
                    continue
            trimmed += segment

        keyword, reply_message = _split_add_arguments(trimmed)
        if not keyword or not reply_message:
            await keyword_command.finish("用法：/关键词 global add <关键词> <回复内容>")

        reply = await _persist_reply_media(reply_message)
        if dm.add_rule(keyword, reply, group_id=None) is None:
            await keyword_command.finish(f"添加失败：全局关键词「{keyword}」已存在。")
        await keyword_command.finish(f"已添加全局关键词「{keyword}」，所有启用关键词回复的群都会生效。")

    if sub_action in {"del", "delete", "删除"}:
        if len(tokens) < 3:
            await keyword_command.finish("用法：/关键词 global del <关键词>")
        if dm.remove_rule(tokens[2], group_id=None):
            await keyword_command.finish(f"已删除全局关键词「{tokens[2]}」。")
        await keyword_command.finish(f"没有找到全局关键词「{tokens[2]}」。")

    await keyword_command.finish(
        "用法：\n"
        "/关键词 global list\n"
        "/关键词 global add <词> <回复>\n"
        "/关键词 global del <词>"
    )
