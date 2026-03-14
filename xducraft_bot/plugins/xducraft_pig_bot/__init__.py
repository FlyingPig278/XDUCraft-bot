import asyncio
import os
import random
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import httpx
from nonebot import get_bots, on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from xducraft_bot.plugins.xducraft_mc_status.utils import is_admin

from .data_manager import pig_data_manager

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_pig_bot",
    description="猪猪图查询与定时推送",
    usage=(
        "用户命令: /pig [关键词]\n"
        "管理员命令: /pig auto on|off, /pig query on|off, /pig status"
    ),
)

PIG_BASE_URL = "https://www.pighub.top"
PIG_ALL_IMAGES_API = f"{PIG_BASE_URL}/api/all-images"
AUTO_PUSH_INTERVAL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 15.0

COMMAND_USAGE = (
    "用法:\n"
    "/pig [关键词] - 随机查询猪猪图\n"
    "/pig auto on|off - 开关本群自动推送\n"
    "/pig query on|off - 开关本群手动查询\n"
    "/pig status - 查看本群开关状态"
)

ENABLE_ACTIONS = {"on", "open", "enable", "start", "开启", "打开", "开", "启用"}
DISABLE_ACTIONS = {"off", "close", "disable", "stop", "关闭", "关", "停用"}

_push_lock = asyncio.Lock()

pig_command = on_command(
    "pig",
    aliases={"猪猪", "piggy"},
    priority=10,
    block=True,
)


def normalize_switch_action(raw_arg: str) -> str:
    action = raw_arg.strip().lower()
    if action in ENABLE_ACTIONS:
        return "enable"
    if action in DISABLE_ACTIONS:
        return "disable"
    return ""


def build_image_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/"):
        return f"{PIG_BASE_URL}{path}"
    return f"{PIG_BASE_URL}/{path}"


def _normalize_image(item: Dict[str, Any]) -> Dict[str, str]:
    title = str(item.get("title", "") or "")
    filename = str(item.get("filename", "") or "")
    image_id = str(item.get("id", "") or "")
    thumbnail = str(item.get("thumbnail", "") or "")
    return {
        "id": image_id,
        "title": title,
        "filename": filename,
        "thumbnail": thumbnail,
        "url": build_image_url(thumbnail),
    }


async def fetch_all_images() -> List[Dict[str, str]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        resp = await client.get(PIG_ALL_IMAGES_API)
        resp.raise_for_status()
        payload = resp.json()

    images = payload.get("images", []) if isinstance(payload, dict) else []
    normalized: List[Dict[str, str]] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        image = _normalize_image(item)
        if image["url"]:
            normalized.append(image)
    return normalized


def find_images_by_keyword(images: List[Dict[str, str]], keyword: str) -> List[Dict[str, str]]:
    kw = keyword.strip().lower()
    if not kw:
        return images

    matched: List[Dict[str, str]] = []
    for image in images:
        haystack = " ".join(
            [
                image.get("title", ""),
                image.get("filename", ""),
                image.get("id", ""),
            ]
        ).lower()
        if kw in haystack:
            matched.append(image)

    if matched:
        return matched

    # Fuzzy fallback: only used when exact-contains has no result.
    if len(kw) < 2:
        return []

    threshold = 0.6 if len(kw) <= 4 else 0.55
    fuzzy_matched: List[Dict[str, str]] = []
    for image in images:
        title = str(image.get("title", "") or "").lower()
        filename = str(image.get("filename", "") or "").lower()
        filename_stem = os.path.splitext(filename)[0]

        candidates = [title, filename, filename_stem]
        best_score = 0.0
        for candidate in candidates:
            if not candidate:
                continue

            score = SequenceMatcher(None, kw, candidate).ratio()
            best_score = max(best_score, score)

            # Improve long-text matching by comparing with same-length windows.
            if len(candidate) > len(kw):
                window_len = max(len(kw), 2)
                for i in range(len(candidate) - window_len + 1):
                    piece = candidate[i : i + window_len]
                    best_score = max(best_score, SequenceMatcher(None, kw, piece).ratio())

        if best_score >= threshold:
            fuzzy_matched.append(image)

    return fuzzy_matched


def pick_random_image(images: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not images:
        return None
    return random.choice(images)


async def _can_manage(bot: Bot, event: GroupMessageEvent) -> bool:
    return await is_admin(bot, event) or await SUPERUSER(bot, event)


async def _send_pig_image(matcher, image: Dict[str, str], prefix: str = "") -> None:
    url = image.get("url", "")
    if not url:
        await matcher.finish("猪猪图地址异常，请稍后重试。")
        return

    await matcher.finish(MessageSegment.image(file=url))


async def _finish_status(matcher, status_text: str) -> None:
    await matcher.finish(status_text)


@pig_command.handle()
async def handle_pig_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()
    arg_list = raw.split()

    if arg_list and arg_list[0].lower() in {"auto", "query", "status", "help"}:
        if not await _can_manage(bot, event):
            await _finish_status(pig_command, "你没有执行该命令的权限")
            return

        subcommand = arg_list[0].lower()
        if subcommand == "help":
            await pig_command.finish(COMMAND_USAGE)
            return

        if subcommand == "status":
            cfg = pig_data_manager.get_group_config(event.group_id)
            await pig_command.finish(
                "本群猪猪插件状态:\n"
                f"自动推送: {'开启' if cfg['auto_push_enabled'] else '关闭'}\n"
                f"手动查询: {'开启' if cfg['query_enabled'] else '关闭'}"
            )
            return

        if len(arg_list) != 2:
            await _finish_status(pig_command, COMMAND_USAGE)
            return

        action = normalize_switch_action(arg_list[1])
        if not action:
            await _finish_status(pig_command, COMMAND_USAGE)
            return

        enabled = action == "enable"
        if subcommand == "auto":
            changed = pig_data_manager.set_auto_push_enabled(event.group_id, enabled)
            if changed:
                await _finish_status(pig_command, f"已{'开启' if enabled else '关闭'}本群自动推送猪猪图")
                return
            await _finish_status(pig_command, f"本群自动推送猪猪图已是{'开启' if enabled else '关闭'}状态")
            return

        changed = pig_data_manager.set_query_enabled(event.group_id, enabled)
        if changed:
            await _finish_status(pig_command, f"已{'开启' if enabled else '关闭'}本群猪猪图查询")
            return
        await _finish_status(pig_command, f"本群猪猪图查询已是{'开启' if enabled else '关闭'}状态")
        return

    cfg = pig_data_manager.get_group_config(event.group_id)
    if not cfg["query_enabled"]:
        await _finish_status(pig_command, "本群已关闭猪猪图查询功能，请联系管理员开启。")
        return

    keyword = raw
    try:
        all_images = await fetch_all_images()
    except Exception as e:
        logger.error("[Pig-Bot] Failed to fetch images: %s", e)
        await _finish_status(pig_command, "获取猪猪图失败，请稍后再试。")
        return

    matched = find_images_by_keyword(all_images, keyword)
    if not matched:
        await _finish_status(pig_command, "没有找到匹配的猪猪图。")
        return

    selected = pick_random_image(matched)
    if not selected:
        await _finish_status(pig_command, "没有可用的猪猪图，请稍后再试。")
        return

    await _send_pig_image(pig_command, selected)


@scheduler.scheduled_job(
    "interval",
    seconds=AUTO_PUSH_INTERVAL_SECONDS,
    id="pig_auto_push_job",
    max_instances=1,
    coalesce=True,
)
async def push_random_pig_job() -> None:
    if _push_lock.locked():
        logger.warning("[Pig-Bot] Previous push job still running, skip this round.")
        return

    async with _push_lock:
        groups = pig_data_manager.list_auto_push_groups()
        if not groups:
            return

        try:
            all_images = await fetch_all_images()
        except Exception as e:
            logger.error("[Pig-Bot] Failed to fetch images for auto push: %s", e)
            return

        image = pick_random_image(all_images)
        if not image:
            logger.warning("[Pig-Bot] No image available for auto push.")
            return

        title = image.get("title", "") or image.get("filename", "") or "猪猪图"
        image_url = image.get("url", "")
        if not image_url:
            logger.warning("[Pig-Bot] Auto push image URL is empty.")
            return

        push_msg = Message()
        push_msg += MessageSegment.text(f"🐷\n标题: {title}\n")
        push_msg += MessageSegment.image(file=image_url)

        bots = get_bots()
        for bot_instance in bots.values():
            for group_id in groups:
                try:
                    await bot_instance.send_group_msg(group_id=group_id, message=push_msg)
                except Exception as e:
                    logger.error("[Pig-Bot] Failed to send group %s: %s", group_id, e)

