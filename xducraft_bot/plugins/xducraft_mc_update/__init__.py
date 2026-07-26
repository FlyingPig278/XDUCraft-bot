import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from nonebot import require, on_command, get_bots
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.log import logger

from xducraft_bot.shared import feature_gate

from .data_manager import data_manager

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="MC更新推送",
    description="监控 Minecraft 官方版本更新并推送到群",
    usage="推荐指令：/MC更新 订阅 或 /MC更新 取消订阅（兼容 /mcup on|off）"
)

FEATURE_KEY = "mc_update"

feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="MC 更新推送",
    description="Minecraft 正式版和快照发布时自动推送",
    default_enabled=False,
    passive=True,
    getter=lambda group_id: int(group_id) in set(data_manager.get_subscribed_groups()),
    setter=lambda group_id, enabled: (
        data_manager.add_group(int(group_id))
        if enabled
        else data_manager.remove_group(int(group_id))
    ),
    lister=data_manager.get_subscribed_groups,
    superuser_only=True,
))

MOJANG_API = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
CHECK_INTERVAL = 60
UTC_PLUS_8 = timezone(timedelta(hours=8))
VERSION_LABELS = {
    "release": "🎉 Minecraft 正式版更新！",
    "snapshot": "🧪 Minecraft 快照版更新！",
}
VERSION_TYPE_NAMES = {
    "release": "正式版",
    "snapshot": "快照版",
}
COMMAND_USAGE = "推荐用法：/MC更新 订阅 或 /MC更新 取消订阅\n兼容写法：/mcup on 或 /mcup off"
ENABLE_ACTIONS = {"on", "open", "enable", "start", "订阅", "开启", "打开", "开", "启用"}
DISABLE_ACTIONS = {"off", "close", "disable", "stop", "取消订阅", "关闭", "关", "停用"}

_check_lock = asyncio.Lock()

mc_command = on_command(
    "mcup",
    aliases={"mcupdate", "MC更新", "mc更新", "更新订阅", "版本订阅", "MC更新订阅"},
    priority=10,
    block=True,
)


def normalize_command_action(raw_arg: str) -> str:
    action = raw_arg.strip().lower()
    if action in ENABLE_ACTIONS:
        return "enable"
    if action in DISABLE_ACTIONS:
        return "disable"
    return ""


@mc_command.handle()
async def handle_mc_command(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        await mc_command.finish("请在群里使用该命令。")
        return

    args = args.extract_plain_text().strip()
    gid = int(group_id)

    if not await SUPERUSER(bot, event):
        return

    action = normalize_command_action(args)

    if not action:
        await mc_command.finish(COMMAND_USAGE)

    if action == "enable":
        if data_manager.add_group(gid):
            await mc_command.finish(f"✅ 已开启 Minecraft 更新推送（群号：{gid}）")
        else:
            await mc_command.finish("⚠️ 这个群已经开启了 Minecraft 更新推送。")

    elif action == "disable":
        if data_manager.remove_group(gid):
            await mc_command.finish(f"🚫 已关闭 Minecraft 更新推送（群号：{gid}）")
        else:
            await mc_command.finish("⚠️ 这个群还没有开启 Minecraft 更新推送。")


def parse_mojang_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def format_release_time(value: str) -> str:
    parsed = parse_mojang_datetime(value)
    if parsed is None:
        return "未知时间"
    return parsed.astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M:%S UTC+8")


def _normalize_manifest_entry(entry: Dict[str, Any]) -> Dict[str, str]:
    return {
        "id": str(entry.get("id", "") or ""),
        "release_time": str(entry.get("releaseTime", "") or ""),
    }


def _is_candidate_newer(candidate: Dict[str, str], current: Dict[str, str]) -> bool:
    candidate_id = str(candidate.get("id", "") or "")
    current_id = str(current.get("id", "") or "")
    if not candidate_id or candidate_id == current_id:
        return False

    candidate_time = parse_mojang_datetime(str(candidate.get("release_time", "") or ""))
    current_time = parse_mojang_datetime(str(current.get("release_time", "") or ""))

    if current_time and candidate_time:
        return candidate_time > current_time
    if not current_time and candidate_time:
        return True

    return False


def get_latest_record(manifest: Dict[str, Any], type_key: str) -> Dict[str, str]:
    target_type = type_key
    latest_entry: Optional[Dict[str, str]] = None
    latest_time: Optional[datetime] = None

    for version in manifest.get("versions", []):
        if version.get("type") != target_type:
            continue

        entry = _normalize_manifest_entry(version)
        if not entry["id"]:
            continue

        entry_time = parse_mojang_datetime(entry["release_time"])
        if latest_entry is None:
            latest_entry = entry
            latest_time = entry_time
            continue

        if entry_time and latest_time:
            if entry_time > latest_time:
                latest_entry = entry
                latest_time = entry_time
        elif entry_time and not latest_time:
            latest_entry = entry
            latest_time = entry_time

    if latest_entry is not None:
        manifest_latest_id = str(manifest.get("latest", {}).get(type_key, "") or "")
        if manifest_latest_id and manifest_latest_id != latest_entry["id"]:
            logger.warning(
                "[MC-Push] Manifest latest.%s=%s is older or inconsistent; use versions entry %s instead.",
                type_key,
                manifest_latest_id,
                latest_entry["id"],
            )
        return latest_entry

    fallback_id = str(manifest.get("latest", {}).get(type_key, "") or "")
    return {"id": fallback_id, "release_time": ""}


def build_update_messages(manifest: Dict[str, Any]) -> List[str]:
    messages: List[str] = []

    for type_key in ("release", "snapshot"):
        latest_record = get_latest_record(manifest, type_key)
        if not latest_record["id"]:
            continue

        cached_record = data_manager.get_last_record(type_key)
        if not cached_record["id"]:
            data_manager.update_version(type_key, latest_record["id"], latest_record["release_time"])
            logger.info("[MC-Push] Init %s: %s", VERSION_TYPE_NAMES[type_key], latest_record["id"])
            continue

        if not _is_candidate_newer(latest_record, cached_record):
            if latest_record["id"] != cached_record["id"]:
                logger.warning(
                    "[MC-Push] Ignore stale %s candidate %s (time=%s), cached=%s (time=%s)",
                    VERSION_TYPE_NAMES[type_key],
                    latest_record["id"],
                    latest_record["release_time"] or "未知",
                    cached_record["id"],
                    cached_record["release_time"] or "未知",
                )
            continue

        if data_manager.update_version(type_key, latest_record["id"], latest_record["release_time"]):
            messages.append(
                f"{VERSION_LABELS[type_key]}\n"
                f"版本号：{latest_record['id']}\n"
                f"发布时间：{format_release_time(latest_record['release_time'])}"
            )

    return messages


@scheduler.scheduled_job("interval", seconds=CHECK_INTERVAL, id="mc_update_checker", max_instances=1, coalesce=True)
async def check_update():
    if _check_lock.locked():
        logger.warning("[MC-Push] Previous update check is still running, skip this round.")
        return

    async with _check_lock:
        groups = data_manager.get_subscribed_groups()
        if not groups:
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(MOJANG_API)
                if resp.status_code != 200:
                    logger.warning(f"[MC-Push] API Error: {resp.status_code}")
                    return

                manifest = resp.json()
                messages = build_update_messages(manifest)

                if not messages:
                    return

                push_msg = "\n\n".join(messages)

                logger.info("[MC-Push] Pushing updates...")
                bots = get_bots()
                for bot in bots.values():
                    for gid in groups:
                        try:
                            await bot.send_group_msg(group_id=gid, message=push_msg)
                        except Exception as e:
                            logger.error(f"[MC-Push] Failed to send group {gid}: {e}")

        except Exception as e:
            logger.error(f"[MC-Push] Exception: {e}")
