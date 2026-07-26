# ruff: noqa: E402

import asyncio
import os
import random
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

import httpx
import jieba
from nonebot import get_bots, on_command, on_message, on_notice, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, GroupRecallNoticeEvent, Message
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from PIL import Image, ImageDraw, ImageFont
from wordcloud import WordCloud

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.permissions import is_admin

from .data_manager import chat_log_data_manager

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_wordcloud",
    description="记录群聊并在每天0点发送词云图",
    usage=(
        "自动功能: 在启用群中记录消息, 每天0点推送前一天词云\n"
        "管理命令: /wc on|off|status|gen [today|yesterday|YYYY-MM-DD|YYYY-MM|all]\n"
        "封禁命令: /wc ban add|del|list [QQ号|@用户]\n"
        "清理命令: /wc clear [QQ号|@用户]"
    ),
)

FEATURE_KEY = "wordcloud"

# 开关状态仍然存在词云自己的 config 里，这里只是把它接进统一面板，
# 这样 /功能 能一次列出所有插件的状态，而不用把已有配置迁移一遍。
feature_gate.register(feature_gate.Feature(
    key=FEATURE_KEY,
    name="群聊词云",
    description="记录群聊文本，每天 0 点推送前一天的词云图",
    default_enabled=False,
    passive=True,
    getter=chat_log_data_manager.is_group_enabled,
    setter=chat_log_data_manager.set_group_enabled,
    lister=chat_log_data_manager.get_enabled_groups,
))

record_group_message = on_message(
    priority=99,
    block=False,
    rule=Rule(lambda event: isinstance(event, GroupMessageEvent)),
)
group_recall_notice = on_notice(
    priority=99,
    block=False,
    rule=Rule(lambda event: isinstance(event, GroupRecallNoticeEvent)),
)
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


def _extract_clean_text(message: Message) -> str:
    text_parts: List[str] = []
    for segment in message:
        if segment.type != "text":
            continue
        text = str(segment.data.get("text", ""))
        if text:
            text_parts.append(text)
    if not text_parts:
        return ""
    merged = "".join(text_parts)
    return re.sub(r"\s+", " ", merged).strip()


def _extract_target_user_id(args: Message, fallback_tokens: List[str]) -> Optional[int]:
    for segment in args:
        if segment.type != "at":
            continue
        qq_value = str(segment.data.get("qq", "")).strip()
        if qq_value.isdigit():
            return int(qq_value)

    for token in fallback_tokens:
        if token.isdigit():
            return int(token)

    return None


def _draw_spaced_text(
    draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font: ImageFont.ImageFont, fill: str, spacing: int
) -> int:
    x, y = xy
    start_x = x
    for index, ch in enumerate(text):
        draw.text((x, y), ch, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), ch, font=font)
        ch_width = bbox[2] - bbox[0]
        x += ch_width
        if index < len(text) - 1:
            x += spacing
    return x - start_x


def _load_random_footer_avatar(avatar_size: int) -> Optional[Image.Image]:
    avatar_dir = Path(__file__).resolve().parent / "data" / "avatars"
    if not avatar_dir.exists():
        return None

    candidates = [
        path
        for path in avatar_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    ]
    if not candidates:
        return None

    avatar_path = random.choice(candidates)
    try:
        with Image.open(avatar_path) as raw_avatar:
            src = raw_avatar.convert("RGBA")
            src_w, src_h = src.size
            crop_side = min(src_w, src_h)
            left = (src_w - crop_side) // 2
            top = (src_h - crop_side) // 2
            src = src.crop((left, top, left + crop_side, top + crop_side))
            avatar = src.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.warning("[WordCloud] Failed to load avatar %s: %s", avatar_path, e)
        return None

    supersample = 4
    mask = Image.new("L", (avatar_size * supersample, avatar_size * supersample), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size * supersample, avatar_size * supersample), fill=255)
    mask = mask.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    avatar.putalpha(mask)
    return avatar


def _download_group_avatar_cached(group_id: int, cache_ttl_seconds: int = 86400) -> Optional[Path]:
    cache_dir = Path(__file__).resolve().parent / "data" / "group_avatar_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"group_{group_id}.png"

    now_ts = datetime.now().timestamp()
    if cache_file.exists() and now_ts - cache_file.stat().st_mtime <= cache_ttl_seconds:
        return cache_file

    avatar_url = f"https://p.qlogo.cn/gh/{group_id}/{group_id}/640"
    try:
        response = httpx.get(avatar_url, timeout=8, follow_redirects=True)
        response.raise_for_status()
        data = response.content
        if data:
            cache_file.write_bytes(data)
            return cache_file
    except Exception as e:
        logger.warning("[WordCloud] Failed to download group avatar for %s: %s", group_id, e)

    return cache_file if cache_file.exists() else None


def _load_group_avatar(group_id: int, avatar_size: int) -> Optional[Image.Image]:
    cache_file = _download_group_avatar_cached(group_id)
    if cache_file is None:
        return None

    try:
        with Image.open(cache_file) as raw_avatar:
            src = raw_avatar.convert("RGBA")
            src_w, src_h = src.size
            crop_side = min(src_w, src_h)
            left = (src_w - crop_side) // 2
            top = (src_h - crop_side) // 2
            src = src.crop((left, top, left + crop_side, top + crop_side))
            avatar = src.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.warning("[WordCloud] Failed to load cached group avatar %s: %s", cache_file, e)
        return None

    supersample = 4
    mask = Image.new("L", (avatar_size * supersample, avatar_size * supersample), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size * supersample, avatar_size * supersample), fill=255)
    mask = mask.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    avatar.putalpha(mask)
    return avatar


def _resolve_footer_texts(output_label: str) -> Tuple[str, str]:
    today = date.today()
    if output_label == "all":
        return "全量词云", "全部记录"

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", output_label):
        return "当日词云", output_label

    if re.fullmatch(r"\d{4}-\d{2}", output_label):
        try:
            target_month = datetime.strptime(output_label + "-01", "%Y-%m-%d").date()
            if target_month.year == today.year and target_month.month == today.month:
                return "本月词云", output_label
            return "月度词云", output_label
        except ValueError:
            return "月度词云", output_label

    return "词云", output_label


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

    cloud_image = Image.fromarray(wordcloud.to_array()).convert("RGB")

    footer_height = 116
    side_padding = 48
    top_padding = 48
    cloud_footer_gap = 24
    branding_options = chat_log_data_manager.get_footer_branding_options()
    branding_enabled = bool(branding_options.get("enabled", True))
    branding_text = str(branding_options.get("text", "")).strip()
    branding_height = 58 if branding_enabled else 0
    bottom_padding = 14 if branding_enabled else 48
    canvas = Image.new(
        "RGB",
        (
            cloud_image.width + side_padding * 2,
            cloud_image.height + cloud_footer_gap + footer_height + branding_height + top_padding + bottom_padding,
        ),
        color="white",
    )
    canvas.paste(cloud_image, (side_padding, top_padding))

    draw = ImageDraw.Draw(canvas)
    font_path = _get_font_path()

    try:
        title_font = ImageFont.truetype(font_path, 58) if font_path else ImageFont.load_default()
        date_font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
        group_font = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()
        branding_font = ImageFont.truetype(font_path, 22) if font_path else ImageFont.load_default()
    except Exception:
        title_font = ImageFont.load_default()
        date_font = ImageFont.load_default()
        group_font = ImageFont.load_default()
        branding_font = ImageFont.load_default()

    title_text, date_text = _resolve_footer_texts(output_label)
    subtitle_text = chat_log_data_manager.get_footer_subtitle()
    group_text = f"群 {group_id}"

    footer_top = top_padding + cloud_image.height + cloud_footer_gap
    footer_inner_x = 36
    left_title_top = 18
    left_subtitle_top = 94
    right_date_top = 14
    right_group_top = 90

    title_x = side_padding + footer_inner_x
    title_y = footer_top + left_title_top
    title_width = _draw_spaced_text(draw, (title_x, title_y), title_text, title_font, "#101010", spacing=8)

    if subtitle_text:
        subtitle_font = group_font
        draw.text((title_x, footer_top + left_subtitle_top), subtitle_text, fill="#a0a0a0", font=subtitle_font)

    date_bbox = draw.textbbox((0, 0), date_text, font=date_font)
    date_width = date_bbox[2] - date_bbox[0]
    right_x = canvas.width - side_padding - footer_inner_x - date_width
    draw.text((right_x, footer_top + right_date_top), date_text, fill="#5a5a5a", font=date_font)

    group_bbox = draw.textbbox((0, 0), group_text, font=group_font)
    group_width = group_bbox[2] - group_bbox[0]
    group_x = canvas.width - side_padding - footer_inner_x - group_width
    draw.text((group_x, footer_top + right_group_top), group_text, fill="#a0a0a0", font=group_font)

    group_avatar_size = 44
    group_avatar = _load_group_avatar(group_id, group_avatar_size)
    if group_avatar is not None:
        title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
        title_height = title_bbox[3] - title_bbox[1]
        avatar_x = title_x + title_width + 16
        avatar_y = title_y + max(0, (title_height - group_avatar_size) // 2)
        if avatar_x + group_avatar_size < right_x - 20:
            canvas.paste(group_avatar, (avatar_x, avatar_y), group_avatar)

    if branding_enabled:
        branding_top = footer_top + footer_height
        my_avatar_size = 28
        my_avatar = _load_random_footer_avatar(my_avatar_size)
        branding_text_width = 0
        branding_text_height = 0
        if branding_text:
            text_bbox = draw.textbbox((0, 0), branding_text, font=branding_font)
            branding_text_width = text_bbox[2] - text_bbox[0]
            branding_text_height = text_bbox[3] - text_bbox[1]

        branding_gap = 10 if (my_avatar is not None and branding_text) else 0
        row_width = branding_text_width + (my_avatar_size if my_avatar is not None else 0) + branding_gap
        row_x = max(side_padding + 8, (canvas.width - row_width) // 2)
        row_height = max(my_avatar_size if my_avatar is not None else 0, branding_text_height)
        row_y = canvas.height - bottom_padding - row_height
        row_y = max(branding_top + 4, row_y)

        if my_avatar is not None:
            canvas.paste(my_avatar, (row_x, row_y), my_avatar)
            row_x += my_avatar_size + branding_gap

        if branding_text:
            text_y = row_y + max(0, (row_height - branding_text_height) // 2)
            draw.text((row_x, text_y), branding_text, fill="#9f9f9f", font=branding_font)

    canvas.save(output_path)
    return output_path


async def _can_manage(bot: Bot, event: GroupMessageEvent) -> bool:
    return await is_admin(bot, event) or await SUPERUSER(bot, event)


def _parse_gen_target(raw_arg: str) -> Optional[Tuple[str, Optional[date]]]:
    arg = (raw_arg or "").strip().lower()
    if not arg or arg == "today":
        return "day", date.today()
    if arg == "yesterday":
        return "day", (date.today() - timedelta(days=1))
    if arg == "all":
        return "all", None
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


async def _generate_and_send_for_group(group_id: int, target_kind: str, target: Optional[date], bot: Bot) -> bool:
    excluded_user_ids = set(chat_log_data_manager.get_ban_user_ids())
    if target_kind == "month":
        if target is None:
            return False
        messages = chat_log_data_manager.get_messages_for_month(
            group_id,
            target.year,
            target.month,
            excluded_user_ids=excluded_user_ids,
        )
        output_label = f"{target.year:04d}-{target.month:02d}"
    elif target_kind == "all":
        messages = chat_log_data_manager.get_messages_for_group(group_id, excluded_user_ids=excluded_user_ids)
        output_label = "all"
    else:
        if target is None:
            target = date.today()
        messages = chat_log_data_manager.get_messages_for_date(group_id, target, excluded_user_ids=excluded_user_ids)
        output_label = target.isoformat()

    if not messages:
        return False

    stopwords = chat_log_data_manager.get_stopwords()
    options = chat_log_data_manager.get_wordcloud_options()
    words = _tokenize_messages(messages, stopwords, options.get("min_word_length", 2))
    # 分词后的绘图、头像下载和 Pillow 合成都属于阻塞工作，放到线程里避免
    # 每次生成词云时卡住机器人的整个事件循环。
    image_path = await asyncio.to_thread(_build_wordcloud_image, group_id, output_label, words)
    if not image_path:
        return False

    await bot.send_group_msg(group_id=group_id, message=f"[CQ:image,file=file:///{image_path}]")
    return True


@record_group_message.handle()
async def handle_group_message_record(event: GroupMessageEvent):
    group_id = int(event.group_id)
    if not chat_log_data_manager.is_group_enabled(group_id):
        return

    if chat_log_data_manager.is_user_banned(int(event.user_id)):
        return

    text = _extract_clean_text(event.message)
    if not text:
        return

    chat_log_data_manager.add_message(
        group_id=group_id,
        message=text,
        message_id=int(event.message_id),
        user_id=int(event.user_id),
    )


@group_recall_notice.handle()
async def handle_group_recall_notice(event: GroupRecallNoticeEvent):
    deleted = chat_log_data_manager.delete_message_by_message_id(
        group_id=int(event.group_id),
        message_id=int(event.message_id),
    )
    if deleted:
        logger.info("[WordCloud] Removed %s recalled row(s) in group %s", deleted, event.group_id)


@wordcloud_command.handle()
async def handle_wordcloud_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not await _can_manage(bot, event):
        await wordcloud_command.finish("你没有执行该命令的权限")
        return

    arg_list = args.extract_plain_text().strip().split()
    if not arg_list:
        await wordcloud_command.finish(
            "用法: /wc on|off|status|gen [today|yesterday|YYYY-MM-DD|YYYY-MM|all] | /wc ban add|del|list [QQ号|@用户] | /wc clear [QQ号|@用户]"
        )
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
            await wordcloud_command.finish("日期格式错误, 请使用 today/yesterday/YYYY-MM-DD/YYYY-MM/all")
            return
        target_kind, target = parsed

        ok = await _generate_and_send_for_group(group_id, target_kind, target, bot)
        if not ok:
            if target_kind == "month":
                assert target is not None
                await wordcloud_command.finish(f"{target.year:04d}-{target.month:02d} 没有可生成词云的聊天记录")
            elif target_kind == "all":
                await wordcloud_command.finish("暂无可生成全量词云的聊天记录")
            else:
                assert target is not None
                await wordcloud_command.finish(f"{target.isoformat()} 没有可生成词云的聊天记录")
            return
        await wordcloud_command.finish()
        return

    if action == "ban":
        if len(arg_list) < 2:
            await wordcloud_command.finish("用法: /wc ban add|del|list [QQ号|@用户]")
            return

        sub_action = arg_list[1].lower()
        if sub_action == "list":
            blocked = chat_log_data_manager.get_ban_user_ids()
            if not blocked:
                await wordcloud_command.finish("当前封禁列表为空")
                return
            preview = "\n".join(str(uid) for uid in blocked[:30])
            suffix = "\n...(仅展示前30项)" if len(blocked) > 30 else ""
            await wordcloud_command.finish(f"当前封禁列表({len(blocked)}):\n{preview}{suffix}")
            return

        if sub_action not in {"add", "del"}:
            await wordcloud_command.finish("未知参数, 用法: /wc ban add|del|list [QQ号|@用户]")
            return

        target_user_id = _extract_target_user_id(args, arg_list[2:])
        if target_user_id is None:
            await wordcloud_command.finish("请提供 QQ号 或 @用户")
            return

        changed = chat_log_data_manager.set_user_banned(target_user_id, banned=(sub_action == "add"))
        if sub_action == "add":
            if changed:
                await wordcloud_command.finish(f"已封禁: {target_user_id}")
                return
            await wordcloud_command.finish(f"该QQ已在封禁列表中: {target_user_id}")
            return

        if changed:
            await wordcloud_command.finish(f"已解封: {target_user_id}")
            return
        await wordcloud_command.finish(f"该QQ不在封禁列表中: {target_user_id}")
        return

    if action == "clear":
        target_user_id = _extract_target_user_id(args, arg_list[1:])
        if target_user_id is None:
            await wordcloud_command.finish("请提供 QQ号 或 @用户")
            return
        deleted = chat_log_data_manager.delete_messages_by_user_id(group_id, target_user_id)
        await wordcloud_command.finish(f"已清除用户 {target_user_id} 在本群的 {deleted} 条词云记录")
        return

    await wordcloud_command.finish(
        "未知参数, 用法: /wc on|off|status|gen [today|yesterday|YYYY-MM-DD|YYYY-MM|all] | /wc ban add|del|list [QQ号|@用户] | /wc clear [QQ号|@用户]"
    )


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

