import httpx
from nonebot import require, on_command, get_bots
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.log import logger
from typing import List, Dict

from .data_manager import data_manager

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="MC更新推送",
    description="监控 Minecraft 官方版本更新并推送到群",
    usage="指令: mcup on / mcup off"
)

MOJANG_API = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
CHECK_INTERVAL = 60

mc_command = on_command("mcup", aliases={"mcupdate"}, priority=10, block=True)


@mc_command.handle()
async def handle_mc_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    args = args.extract_plain_text().strip().lower()
    gid = event.group_id

    if not await SUPERUSER(bot, event):
        return

    if args == "on":
        if data_manager.add_group(gid):
            await mc_command.finish(f"✅ [MC-Push] Subscribed (Group: {gid})")
        else:
            await mc_command.finish("⚠️ Already subscribed.")

    elif args == "off":
        if data_manager.remove_group(gid):
            await mc_command.finish(f"🚫 [MC-Push] Unsubscribed (Group: {gid})")
        else:
            await mc_command.finish("⚠️ Not subscribed yet.")


# --- 辅助函数：根据版本号查找发布时间 ---
def get_version_time(version_id: str, versions_list: List[Dict]) -> str:
    for v in versions_list:
        if v.get("id") == version_id:
            # 这里的 releaseTime 是 UTC 时间，格式如 2026-02-17T12:42:24+00:00
            # 如果你想转成北京时间，可以用 datetime 库处理，这里暂时原样返回
            return v.get("releaseTime", "Unknown Time")
    return "Unknown Time"


@scheduler.scheduled_job("interval", seconds=CHECK_INTERVAL, id="mc_update_checker")
async def check_update():
    groups = data_manager.get_subscribed_groups()
    if not groups:
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(MOJANG_API)
            if resp.status_code != 200:
                logger.warning(f"[MC-Push] API Error: {resp.status_code}")
                return

            data = resp.json()
            latest = data.get("latest", {})
            versions_list = data.get("versions", [])

            current_release = latest.get("release")
            current_snapshot = latest.get("snapshot")

            messages = []

            # --- 检查正式版 ---
            cached_release = data_manager.get_last_version("release")
            if not cached_release:
                data_manager.update_version("release", current_release)
                logger.info(f"[MC-Push] Init Release: {current_release}")
            elif current_release != cached_release:
                data_manager.update_version("release", current_release)
                # 查找具体时间
                r_time = get_version_time(current_release, versions_list)
                messages.append(f"🎉 Minecraft New Release!\nVersion: {current_release}\nTime: {r_time}")

            # --- 检查快照版 ---
            cached_snapshot = data_manager.get_last_version("snapshot")
            if not cached_snapshot:
                data_manager.update_version("snapshot", current_snapshot)
                logger.info(f"[MC-Push] Init Snapshot: {current_snapshot}")
            elif current_snapshot != cached_snapshot:
                data_manager.update_version("snapshot", current_snapshot)
                # 查找具体时间
                s_time = get_version_time(current_snapshot, versions_list)
                messages.append(f"🧪 Minecraft New Snapshot!\nVersion: {current_snapshot}\nTime: {s_time}")

            # --- 发送 ---
            if messages:
                push_msg = "\n\n".join(messages)  # 如果两个同时更，用空行隔开

                logger.info(f"[MC-Push] Pushing updates...")
                bots = get_bots()
                for bot in bots.values():
                    for gid in groups:
                        try:
                            await bot.send_group_msg(group_id=gid, message=push_msg)
                        except Exception as e:
                            logger.error(f"[MC-Push] Failed to send group {gid}: {e}")

    except Exception as e:
        logger.error(f"[MC-Push] Exception: {e}")