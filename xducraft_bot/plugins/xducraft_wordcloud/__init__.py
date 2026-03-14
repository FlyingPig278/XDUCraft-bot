import os
import re
import warnings
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set, Tuple

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    module=r"jieba\._compat",
)

import jieba
from nonebot import get_bots, on_command, on_message, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from wordcloud import WordCloud

from xducraft_bot.plugins.xducraft_mc_status.utils import is_admin

from .data_manager import chat_log_data_manager

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_wordcloud",
    description="记录群聊并在每天0点发送词云图",
    usage=(
        "自动功能: 在启用群中记录消息, 每天0点推送前一天词云\n"
        "管理命令: /wc on|off|status|gen [today|yesterday|YYYY-MM-DD|YYYY-MM]"
    ),
)

record_group_message = on_message(priority=99, block=False)
wordcloud_command = on_command("wc", aliases={"词云", "wordcloud"}, priority=10, block=True)


def _get_font_path() -> Optional[str]:
    # Reuse existing Chinese font resource in this repository when available.
    candidate = (
        Path(__file__).resolve().parents[1]
        / "xducraft_mc_status"
        / "resources"
        / "fonts"
        / "SourceHanSansCN-Medium.otf"
    )
    if candidate.exists():
        return str(candidate)
    return None


def _tokenize_messages(messages: List[str], stopwords: Set[str], min_word_length: int) -> List[str]:
    words: List[str] = []
    for message in messages:
        for token in jieba.lcut(message):
            clean = token.strip().lower()
            if not clean:
                continue
            if len(clean) < min_word_length:
                continue
            if clean in stopwords:
                continue
            if clean.isdigit():
                continue
            if re.fullmatch(r"[\W_]+", clean):
                continue
            words.append(clean)
    return words


def _build_wordcloud_image(group_id: int, output_label: str, words: List[str]) -> Optional[str]:
    if not words:
        return None

    output_dir = os.path.join(os.path.dirname(__file__), "data", "images")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"wordcloud_{group_id}_{output_label}.png")
    frequencies = Counter(words)
    options = chat_log_data_manager.get_wordcloud_options()

    wordcloud = WordCloud(
        width=1200,
        height=800,
        background_color="white",
        font_path=_get_font_path(),
        collocations=False,
        max_words=options.get("max_words", 200),
    )
    wordcloud.generate_from_frequencies(frequencies)
    wordcloud.to_file(output_path)
    return output_path


async def _can_manage(bot: Bot, event: GroupMessageEvent) -> bool:
    return await is_admin(bot, event) or await SUPERUSER(bot, event)


def _parse_gen_target(raw_arg: str) -> Optional[Tuple[str, date]]:
    arg = (raw_arg or "").strip().lower()
    if not arg or arg == "today":
        return "day", date.today()
    if arg == "yesterday":
        return "day", (date.today() - timedelta(days=1))
    if re.fullmatch(r"\d{4}-\d{2}", arg):
        try:
            month_start = datetime.strptime(arg + "-01", "%Y-%m-%d").date()
            return "month", month_start
        except ValueError:
            return None
    try:
        return "day", datetime.strptime(arg, "%Y-%m-%d").date()
    except ValueError:
        return None


async def _generate_and_send_for_group(group_id: int, target_kind: str, target: date, bot: Bot) -> bool:
    if target_kind == "month":
        messages = chat_log_data_manager.get_messages_for_month(group_id, target.year, target.month)
        output_label = f"{target.year:04d}-{target.month:02d}"
    else:
        messages = chat_log_data_manager.get_messages_for_date(group_id, target)
        output_label = target.isoformat()

    if not messages:
        return False

    stopwords = chat_log_data_manager.get_stopwords()
    options = chat_log_data_manager.get_wordcloud_options()
    words = _tokenize_messages(messages, stopwords, options.get("min_word_length", 2))
    image_path = _build_wordcloud_image(group_id, output_label, words)
    if not image_path:
        return False

    await bot.send_group_msg(group_id=group_id, message=f"[CQ:image,file=file:///{image_path}]")
    return True


@record_group_message.handle()
async def handle_group_message_record(event: GroupMessageEvent):
    group_id = int(event.group_id)
    if not chat_log_data_manager.is_group_enabled(group_id):
        return

    text = event.get_plaintext().strip()
    if not text:
        return

    chat_log_data_manager.add_message(group_id=group_id, message=text)


@wordcloud_command.handle()
async def handle_wordcloud_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not await _can_manage(bot, event):
        await wordcloud_command.finish("你没有执行该命令的权限")
        return

    arg_list = args.extract_plain_text().strip().split()
    if not arg_list:
        await wordcloud_command.finish("用法: /wc on|off|status|gen [today|yesterday|YYYY-MM-DD|YYYY-MM]")
        return

    action = arg_list[0].lower()
    group_id = int(event.group_id)

    if action == "on":
        changed = chat_log_data_manager.set_group_enabled(group_id, True)
        if changed:
            await wordcloud_command.finish("已开启本群词云记录与推送")
            return
        await wordcloud_command.finish("本群词云记录与推送已开启")
        return

    if action == "off":
        changed = chat_log_data_manager.set_group_enabled(group_id, False)
        if changed:
            await wordcloud_command.finish("已关闭本群词云记录与推送")
            return
        await wordcloud_command.finish("本群词云记录与推送已关闭")
        return

    if action == "status":
        enabled = chat_log_data_manager.is_group_enabled(group_id)
        await wordcloud_command.finish(f"本群词云状态: {'开启' if enabled else '关闭'}")
        return

    if action == "gen":
        parsed = _parse_gen_target(arg_list[1] if len(arg_list) > 1 else "")
        if parsed is None:
            await wordcloud_command.finish("日期格式错误, 请使用 today/yesterday/YYYY-MM-DD/YYYY-MM")
            return
        target_kind, target = parsed

        ok = await _generate_and_send_for_group(group_id, target_kind, target, bot)
        if not ok:
            if target_kind == "month":
                await wordcloud_command.finish(f"{target.year:04d}-{target.month:02d} 没有可生成词云的聊天记录")
            else:
                await wordcloud_command.finish(f"{target.isoformat()} 没有可生成词云的聊天记录")
            return
        await wordcloud_command.finish()
        return

    await wordcloud_command.finish("未知参数, 用法: /wc on|off|status|gen [today|yesterday|YYYY-MM-DD|YYYY-MM]")


@scheduler.scheduled_job("cron", hour=0, minute=0, id="xducraft_daily_wordcloud", max_instances=1, coalesce=True)
async def daily_wordcloud_push() -> None:
    target_date = date.today() - timedelta(days=1)
    retention_days = chat_log_data_manager.get_retention_days()
    enabled_groups = chat_log_data_manager.get_enabled_groups()

    if not enabled_groups:
        chat_log_data_manager.cleanup_old_messages(keep_days=retention_days, ref_date=date.today())
        return

    bots = get_bots()
    bot = next(iter(bots.values()), None)
    if bot is None:
        logger.warning("[WordCloud] No available bot instance, skip daily push.")
        return

    for group_id in enabled_groups:
        try:
            ok = await _generate_and_send_for_group(group_id, "day", target_date, bot)
            if not ok:
                logger.info("[WordCloud] Group %s has no valid tokens on %s.", group_id, target_date.isoformat())
        except Exception as e:
            logger.error("[WordCloud] Failed to send group %s: %s", group_id, e)

    deleted = chat_log_data_manager.cleanup_old_messages(keep_days=retention_days, ref_date=date.today())
    if deleted:
        logger.info("[WordCloud] Cleanup old chat rows: %s", deleted)

