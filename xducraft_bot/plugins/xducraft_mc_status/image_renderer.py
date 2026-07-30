"""把服务器状态树渲染成 Minecraft 风格状态图。

布局沿用 ``koishi-plugin-mcsm-portal`` 的信息骨架，但针对群聊图片做了收束：

- 顶部左侧是品牌、标题和数据源，右侧是在线服务器 / 在线玩家概览胶片；
- 每台服务器回到紧凑固定高度；图标无边框，正文只保留两行 MOTD；
- MOTD 为空或为默认 ``A Minecraft Server`` 时，改画配置里的备注名称；
- Tag 在右上角、紧贴延迟左侧；延迟、人数、版本继续组成紧凑状态栈；
- 验证方式颜色只留在左边条，实测为实线，仅配置为虚线；
- 图例留在材质区，群公告与署名进入底部透明到黑色的渐变压角。

所有文字默认由 :class:`.raster.Canvas` 做 Minecraft 式两遍投影。
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from nonebot.log import logger
from PIL import Image, ImageColor, ImageFile

from . import auth_mode as auth
from . import tokens as t
from .constants import (
    DEFAULT_SERVER_ICON_PATH,
    OFFLINE_SERVER_ICON_PATH,
    RENDERED_IMAGE_TTL,
    SAVE_IMG_DIR,
)
from .data_manager import get_footer, get_group_default_auth_mode
from .decode_image import decode_image
from .drawing_utils import Segment, as_rgba, parse_minecraft_formatting, wrap_segments
from .fonts import ADDRESS, CHIP, DATA, EYEBROW, MICRO, MOTD, SUBTITLE, TITLE, VERSION
from .raster import Canvas, TIER_BARS, TIER_COLORS, ink_for_background, list_textures, ping_tier
from .settings import (
    NO_TEXTURE,
    PER_GROUP_TEXTURE,
    RANDOM_TEXTURE,
    RenderSettings,
    current as current_settings,
)
from .status_fetcher import prepare_data_for_display, preprocess_server_data, summarize

from .utils import get_server_display_address
ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_ICON_PIXELS = 2048 * 2048
FALLBACK_TEXTURE = "stone.png"

# 顶部垂直节奏。
HEADER_ROW_EYEBROW = 16
HEADER_ROW_TITLE = 44
HEADER_ROW_SUBTITLE = 20
HEADER_RULE_GAP = 6

# 精简卡片保留两行 MOTD 和一行底部地址；右侧是 Tag + 三项紧凑状态栈。
ROW_MOTD_Y = (18, 40)
ROW_META_Y = 68
RAIL_ROW_Y = (16, 34, 52)
LATENCY_SIGNAL_GAP = 4
LATENCY_UNIT_GAP = 2

# 信号条。
BAR_WIDTH = 3
BAR_GAP = 2
BAR_STEP = 2
BAR_BASE = 3


@dataclass(frozen=True)
class HeaderMetrics:
    eyebrow_y: Optional[float]
    title_y: Optional[float]
    subtitle_y: float
    rule_y: float
    list_top: float


def header_metrics(settings: RenderSettings) -> HeaderMetrics:
    """根据可选品牌 / 标题行计算顶部高度；空行不占空间。"""
    cursor = t.PAGE_PADDING_TOP
    eyebrow_y = title_y = None
    if settings.brand.strip():
        eyebrow_y = cursor + HEADER_ROW_EYEBROW / 2
        cursor += HEADER_ROW_EYEBROW
    if settings.title.strip():
        title_y = cursor + HEADER_ROW_TITLE / 2
        cursor += HEADER_ROW_TITLE
    subtitle_y = cursor + HEADER_ROW_SUBTITLE / 2
    cursor += HEADER_ROW_SUBTITLE
    rule_y = cursor + HEADER_RULE_GAP
    return HeaderMetrics(
        eyebrow_y=eyebrow_y,
        title_y=title_y,
        subtitle_y=subtitle_y,
        rule_y=rule_y,
        list_top=rule_y + t.SECTION_GAP,
    )


@dataclass
class CardLayout:
    """一张固定高服务器卡片的绝对坐标（逻辑单位）。"""

    node: Dict[str, Any]
    level: int
    top: float
    height: float = t.CARD_HEIGHT
    children: List["CardLayout"] = field(default_factory=list)

    @property
    def left(self) -> float:
        return t.PAGE_PADDING_X + self.level * t.CHILD_INDENT

    @property
    def box_left(self) -> float:
        return self.left + t.AUTH_STRIPE_WIDTH

    @property
    def right(self) -> float:
        return t.CANVAS_WIDTH - t.PAGE_PADDING_X

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def icon_left(self) -> float:
        return self.box_left + t.CARD_PAD

    @property
    def icon_top(self) -> float:
        return self.top + t.CARD_PAD

    @property
    def icon_center_y(self) -> float:
        return self.icon_top + t.ICON_SIZE / 2

    @property
    def body_left(self) -> float:
        return self.icon_left + t.ICON_SIZE + t.CARD_COL_GAP

    @property
    def rail_right(self) -> float:
        return self.right - t.CARD_PAD

    @property
    def rail_left(self) -> float:
        return self.rail_right - t.RAIL_WIDTH

    @property
    def body_right(self) -> float:
        return self.rail_left - t.CARD_COL_GAP

    @property
    def body_width(self) -> float:
        return max(0.0, self.body_right - self.body_left)


def build_layout(
    nodes: List[Dict[str, Any]], start_y: float, level: int = 0,
) -> Tuple[List[CardLayout], float]:
    """按深度优先顺序排版；无论玩家列表是否存在，所有行都固定高。"""
    cards: List[CardLayout] = []
    cursor = start_y
    for node in nodes:
        card = CardLayout(node=node, level=level, top=cursor)
        cursor += t.CARD_HEIGHT + t.CARD_GAP
        children = node.get("children") or []
        if children:
            card.children, cursor = build_layout(children, cursor, level + 1)
        cards.append(card)
    return cards, cursor


def _iter_cards(cards: Sequence[CardLayout]) -> Iterable[CardLayout]:
    for card in cards:
        yield card
        yield from _iter_cards(card.children)


def _iter_nodes(nodes: Sequence[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for node in nodes:
        yield node
        yield from _iter_nodes(node.get("children") or [])


def band_is_visible(settings: RenderSettings, footer_text: str = "") -> bool:
    return bool(footer_text.strip() or settings.credit.strip() or settings.show_generated_at)


def band_height(footer_text: str, credit_row: bool = True) -> float:
    """底部内容高度。渐变可以向上溢出，但只为实际文字保留空间。"""
    height = 2 * t.BAND_PADDING_Y
    if footer_text.strip():
        height += t.BAND_NOTICE_HEIGHT
    if footer_text.strip() and credit_row:
        height += t.BAND_LINE_GAP
    if credit_row:
        height += t.BAND_CREDIT_HEIGHT
    return height


def calculate_image_height(
    list_top: float,
    list_height: float,
    footer_text: str,
    legend_modes: Sequence[str],
    band: bool = True,
    min_height: Optional[float] = None,
) -> float:
    total = list_top + list_height + t.PAGE_PADDING_BOTTOM
    if legend_modes:
        total += t.LEGEND_HEIGHT + t.SECTION_GAP
    if band:
        total += band_height(footer_text)
    floor = t.CANVAS_MIN_HEIGHT if min_height is None else min_height
    return max(total, floor)


# ------------------------------------------------------------------------------
# 验证方式与材质
# ------------------------------------------------------------------------------


def _resolve_rendered_auth(
    server_data: Dict[str, Any], group_default: str,
) -> Optional[auth.ResolvedAuth]:
    configured = auth.normalize_mode(server_data.get("auth_mode")) or ""
    inherited = auth.normalize_mode(group_default) or ""
    if not configured and not inherited:
        return None
    return auth.resolve_auth(server_data, group_default)


def _collect_auth_modes(cards: Sequence[CardLayout], group_default: str) -> List[str]:
    present = {
        resolved.mode
        for card in cards
        if (resolved := _resolve_rendered_auth(card.node, group_default)) is not None
        and resolved.mode != auth.MODE_UNKNOWN
    }
    order = (
        auth.MODE_OFFICIAL,
        auth.MODE_MUA,
        auth.MODE_XDU,
        auth.MODE_YGGDRASIL,
        auth.MODE_OFFLINE,
        auth.MODE_MIXED,
    )
    return [mode for mode in order if mode in present]


def resolve_texture(settings: RenderSettings, group_id: int) -> str:
    textures = list_textures()
    if not textures:
        return ""
    choice = (settings.texture or PER_GROUP_TEXTURE).strip()
    if choice == NO_TEXTURE:
        return ""
    if choice == RANDOM_TEXTURE:
        return random.choice(textures)
    if choice:
        if choice in textures:
            return choice
        logger.warning("[MCStatus] 配置的背景材质 {} 不存在，改用 {}。", choice, FALLBACK_TEXTURE)
        return FALLBACK_TEXTURE if FALLBACK_TEXTURE in textures else textures[0]
    return textures[zlib.crc32(str(group_id).encode("utf-8")) % len(textures)]


# ------------------------------------------------------------------------------
# 顶部、图例、底部
# ------------------------------------------------------------------------------


HEADER_STATUS_DOT = 4
HEADER_STATUS_DOT_GAP = 6


def _draw_header_statuses(
    canvas: Canvas, stats: Dict[str, int], right: float, center_y: float,
) -> float:
    """右对齐的纯文字概览；每项用一个绿色像素点引导，不再套胶片。"""
    items = (
        f"{stats['online']}/{stats['total']}服务器在线",
        f"{stats['players_online']}人在线",
    )
    widths = [HEADER_STATUS_DOT + HEADER_STATUS_DOT_GAP + canvas.measure(text, CHIP) for text in items]
    total = sum(widths) + t.HEADER_STATUS_GAP
    cursor = right - total
    start = cursor
    for index, (text, width) in enumerate(zip(items, widths)):
        dot_y = center_y - HEADER_STATUS_DOT / 2
        canvas.rect(
            (cursor, dot_y, cursor + HEADER_STATUS_DOT, dot_y + HEADER_STATUS_DOT),
            fill=t.STATE_EXCELLENT,
        )
        canvas.text(
            text, (cursor + HEADER_STATUS_DOT + HEADER_STATUS_DOT_GAP, center_y),
            CHIP, t.INK_STRONG, "lm",
        )
        cursor += width + (t.HEADER_STATUS_GAP if index == 0 else 0)
    return start


def _draw_header(
    canvas: Canvas,
    stats: Dict[str, int],
    source_label: str,
    metrics: HeaderMetrics,
    settings: RenderSettings,
) -> None:
    left = t.PAGE_PADDING_X
    right = t.CANVAS_WIDTH - t.PAGE_PADDING_X
    status_y = metrics.title_y or metrics.subtitle_y

    status_left = _draw_header_statuses(canvas, stats, right, status_y)
    text_limit = max(0.0, status_left - t.HEADER_GAP - left)

    if metrics.eyebrow_y is not None:
        canvas.segments(
            canvas.fit(parse_minecraft_formatting(settings.brand, t.INK_MUTED), EYEBROW, text_limit),
            (left, metrics.eyebrow_y), EYEBROW, "lm",
        )
    if metrics.title_y is not None:
        canvas.segments(
            canvas.fit(parse_minecraft_formatting(settings.title, t.INK), TITLE, text_limit),
            (left, metrics.title_y), TITLE, "lm",
        )

    subtitle = f"数据源 {source_label}" if source_label else "Minecraft Server Status"
    canvas.text(
        canvas.fit_text(subtitle, SUBTITLE, text_limit),
        (left, metrics.subtitle_y), SUBTITLE, t.INK_FAINT, "lm",
    )
    canvas.hline(metrics.rule_y, left, right, t.RULE)


def _draw_legend(canvas: Canvas, modes: Sequence[str], top: float) -> None:
    """只解释验证方式颜色；实线 / 虚线直接由形状表达，不再放说明句。"""
    center_y = top + t.LEGEND_HEIGHT / 2
    cursor = t.PAGE_PADDING_X
    limit = t.CANVAS_WIDTH - t.PAGE_PADDING_X
    for mode in modes:
        style = auth.style_for(mode)
        label = style.label
        width = t.LEGEND_SWATCH + 6 + canvas.measure(label, MICRO)
        if cursor + width > limit:
            break
        canvas.rect(
            (cursor, center_y - t.LEGEND_SWATCH / 2,
             cursor + t.LEGEND_SWATCH, center_y + t.LEGEND_SWATCH / 2),
            fill=style.color,
            outline=t.RULE,
            width=1,
        )
        canvas.text(label, (cursor + t.LEGEND_SWATCH + 6, center_y), MICRO, t.INK_FAINT, "lm")
        cursor += width + t.LEGEND_GAP


def _draw_band(
    canvas: Canvas,
    image_height: float,
    footer_text: str,
    settings: RenderSettings,
) -> None:
    credit_row = bool(settings.credit.strip() or settings.show_generated_at)
    content_height = band_height(footer_text, credit_row)
    content_top = image_height - content_height
    gradient_top = min(content_top, image_height - t.BAND_VIGNETTE)
    canvas.vertical_gradient(
        (0, gradient_top, t.CANVAS_WIDTH, image_height),
        (0, 0, 0, 0),
        t.BAND_BOTTOM,
    )

    cursor = content_top + t.BAND_PADDING_Y
    if footer_text.strip():
        canvas.text(
            canvas.fit_text(footer_text.strip(), SUBTITLE, t.CANVAS_WIDTH - 2 * t.PAGE_PADDING_X),
            (t.PAGE_PADDING_X, cursor + t.BAND_NOTICE_HEIGHT / 2),
            SUBTITLE,
            t.INK_STRONG,
            "lm",
        )
        cursor += t.BAND_NOTICE_HEIGHT + (t.BAND_LINE_GAP if credit_row else 0)

    if not credit_row:
        return
    center_y = cursor + t.BAND_CREDIT_HEIGHT / 2
    half = t.CANVAS_WIDTH / 2 - t.PAGE_PADDING_X
    if settings.credit.strip():
        canvas.segments(
            canvas.fit(parse_minecraft_formatting(settings.credit, t.INK_FAINT), MICRO, half),
            (t.PAGE_PADDING_X, center_y), MICRO, "lm",
        )
    if settings.show_generated_at:
        canvas.text(
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            (t.CANVAS_WIDTH - t.PAGE_PADDING_X, center_y), MICRO, t.INK_FAINT, "rm",
        )


# ------------------------------------------------------------------------------
# 卡片
# ------------------------------------------------------------------------------


def _auth_color(resolved: Optional[auth.ResolvedAuth]):
    if resolved is None or resolved.mode == auth.MODE_UNKNOWN:
        return t.RULE
    return as_rgba(resolved.style.color)


def _draw_auth_stripe(canvas: Canvas, card: CardLayout, resolved: Optional[auth.ResolvedAuth]) -> None:
    color = _auth_color(resolved)
    if resolved is None or resolved.mode == auth.MODE_UNKNOWN or resolved.confirmed:
        canvas.rect((card.left, card.top, card.box_left, card.bottom), fill=color)
    else:
        cursor = card.top
        while cursor < card.bottom:
            canvas.rect(
                (card.left, cursor, card.box_left, min(cursor + t.AUTH_DASH, card.bottom)),
                fill=color,
            )
            cursor += t.AUTH_DASH + t.AUTH_DASH_GAP
    if resolved is not None and resolved.conflict:
        canvas.rect(
            (card.left, card.top, card.box_left, min(card.top + t.AUTH_DASH, card.bottom)),
            fill=t.AUTH_CONFLICT_COLOR,
        )


def _draw_card_shell(
    canvas: Canvas,
    card: CardLayout,
    resolved: Optional[auth.ResolvedAuth],
    online: bool,
) -> None:
    canvas.rect(
        (card.box_left, card.top, card.right, card.bottom),
        fill=t.SURFACE if online else t.SURFACE_IDLE,
        outline=t.RULE,
    )
    _draw_auth_stripe(canvas, card, resolved)


async def _load_icon(server_data: Dict[str, Any]) -> Optional[Image.Image]:
    size = t.px(t.ICON_SIZE)
    favicon = server_data.get("favicon")
    if favicon:
        try:
            icon_bytes = await decode_image(favicon)
            if icon_bytes:
                with Image.open(icon_bytes) as raw:
                    if raw.width <= 0 or raw.height <= 0 or raw.width * raw.height > MAX_ICON_PIXELS:
                        raise ValueError("favicon 像素数超过上限")
                    return _fit_icon(raw.convert("RGBA"), size)
        except Exception as exc:
            logger.debug("[MCStatus] favicon 解码失败 {}: {}", server_data.get("ip"), exc)
    return _builtin_icon(bool(server_data.get("online")))


def _fit_icon(icon: Image.Image, size: int) -> Image.Image:
    if icon.size == (size, size):
        return icon
    # Java 服务器 favicon 本来就是 64×64 像素画；即使目标不是整数倍，也宁可
    # 保留硬边和不等宽像素块，不用 Lanczos 把它抹成一张模糊缩略图。
    resample = Image.Resampling.NEAREST if icon.width == icon.height else Image.Resampling.LANCZOS
    return icon.resize((size, size), resample)


@lru_cache(maxsize=4)
def _builtin_icon(online: bool) -> Optional[Image.Image]:
    path = DEFAULT_SERVER_ICON_PATH if online else OFFLINE_SERVER_ICON_PATH
    try:
        with Image.open(path) as raw:
            return _fit_icon(raw.convert("RGBA"), t.px(t.ICON_SIZE))
    except Exception as exc:
        logger.warning("[MCStatus] 内置图标加载失败 {}: {}", path, exc)
        return None


def _draw_icon(canvas: Canvas, icon: Optional[Image.Image], card: CardLayout, online: bool) -> None:
    if icon is not None:
        # 图标本身已有清楚的像素轮廓；不再套一层与卡片重复的边框。
        canvas.paste(icon, card.icon_left, card.icon_top)


DEFAULT_MOTD_TEXTS = frozenset({
    "a minecraft server",
    "a minecraft server (the default server motd)",
})


def _tag_background(tag_color: str):
    raw = str(tag_color or "").strip()
    if raw and not raw.startswith("#"):
        raw = f"#{raw}"
    try:
        return as_rgba(ImageColor.getcolor(raw, "RGBA"))
    except (TypeError, ValueError):
        return t.CHIP


def _rich_segments(text: str, color=t.INK, *, html: bool = False) -> List[Segment]:
    lowered = text.lower()
    rich_markup = html or any(
        marker in lowered
        for marker in ("<gradient:", "<font ", "<b>", "<strong>", "<i>", "<u>")
    )
    return parse_minecraft_formatting(text, color, is_html=rich_markup)


def _is_default_motd(text: str) -> bool:
    return text.strip().casefold() in DEFAULT_MOTD_TEXTS


def _remark_segments(server_data: Dict[str, Any]) -> List[Segment]:
    remark = str(server_data.get("comment") or "").strip()
    if remark:
        return _rich_segments(remark)
    fallback = "服务器离线" if not server_data.get("online") else "未设置服务器备注"
    return parse_minecraft_formatting(fallback, t.INK_GHOST)


def _motd_segments(server_data: Dict[str, Any]) -> List[Segment]:
    """正常画 MOTD；空值或默认 MOTD 改用配置备注，不再另画服务器标题。"""
    description = server_data.get("description")
    if isinstance(description, dict):
        html = str(description.get("html") or "").strip()
        plain = str(description.get("text") or "").strip()
        raw = (html or plain).replace("服务器已离线...", "").strip()
        probe = plain or raw
        if raw and not _is_default_motd(probe):
            return _rich_segments(raw, html=bool(html))
        return _remark_segments(server_data)
    if isinstance(description, str):
        raw = description.strip()
        if raw and not _is_default_motd(raw):
            return _rich_segments(raw)
    return _remark_segments(server_data)


def _draw_motd_rows(canvas: Canvas, card: CardLayout) -> None:
    lines = wrap_segments(
        _motd_segments(card.node), MOTD, card.body_width * t.SCALE, t.MOTD_LINES,
    )
    for index, line in enumerate(lines[:t.MOTD_LINES]):
        canvas.segments(
            line, (card.body_left, card.top + ROW_MOTD_Y[index]), MOTD, "lm",
        )


def _draw_meta_row(
    canvas: Canvas,
    card: CardLayout,
    address: str,
    resolved: Optional[auth.ResolvedAuth],
) -> None:
    """底部地址行；验证方式降级成紧随其后的彩色下划线文字。"""
    center_y = card.top + ROW_META_Y
    label = ""
    label_width = 0.0
    if resolved is not None and resolved.mode != auth.MODE_UNKNOWN:
        label = resolved.style.short_label
        label_width = canvas.measure(label, ADDRESS)
    gap = 8 if label else 0
    address_budget = max(0.0, card.body_width - label_width - gap)
    address_text = canvas.fit_text(address, ADDRESS, address_budget)
    address_width = canvas.text(
        address_text, (card.body_left, center_y), ADDRESS, t.INK_FAINT, "lm",
    )
    if label:
        canvas.segments(
            [Segment(label, _auth_color(resolved), underline=True)],
            (card.body_left + address_width + gap, center_y), ADDRESS, "lm",
        )


def _draw_tag_right(
    canvas: Canvas, card: CardLayout, right: float, center_y: float,
) -> Optional[Tuple[float, float, float, float]]:
    """把 Tag 胶片的右边缘锚在延迟文本左侧。"""
    tag = str(card.node.get("tag") or "").strip()
    if not tag:
        return None
    background = _tag_background(str(card.node.get("tag_color") or ""))
    label_budget = t.TAG_CHIP_MAX_WIDTH - 2 * t.TAG_CHIP_PADDING_X
    label = canvas.fit_text(tag, CHIP, label_budget)
    width = min(
        t.TAG_CHIP_MAX_WIDTH,
        canvas.measure(label, CHIP) + 2 * t.TAG_CHIP_PADDING_X,
    )
    left = right - width
    box = (
        left, center_y - t.TAG_CHIP_HEIGHT / 2,
        right, center_y + t.TAG_CHIP_HEIGHT / 2,
    )
    canvas.rect(box, fill=background, outline=t.RULE, width=1)
    canvas.text(
        label, (right - t.TAG_CHIP_PADDING_X, center_y), CHIP,
        ink_for_background(background), "rm",
    )
    return box


def _draw_signal(canvas: Canvas, right: float, center_y: float, tier: str) -> float:
    active = TIER_BARS[tier]
    color = TIER_COLORS[tier]
    width = t.SIGNAL_BARS * BAR_WIDTH + (t.SIGNAL_BARS - 1) * BAR_GAP
    bottom = center_y + (BAR_BASE + t.SIGNAL_BARS * BAR_STEP) / 2
    left = right - width
    for index in range(t.SIGNAL_BARS):
        height = BAR_BASE + index * BAR_STEP
        x = left + index * (BAR_WIDTH + BAR_GAP)
        canvas.rect(
            (x, bottom - height, x + BAR_WIDTH, bottom),
            fill=color if index < active else t.RULE,
        )
    return width


def _draw_rail(canvas: Canvas, card: CardLayout) -> None:
    """右侧状态栈；Tag 右对齐到延迟文字左侧。"""
    node = card.node
    online = bool(node.get("online"))
    ping = int(node.get("ping") or 0) if online else None
    tier = ping_tier(ping, online)
    right = card.rail_right
    ping_y, players_y, version_y = (card.top + offset for offset in RAIL_ROW_Y)

    bars = _draw_signal(canvas, right, ping_y, tier)
    unit_right = right - bars - LATENCY_SIGNAL_GAP
    if not online:
        label = "离线"
        latency_left = unit_right - canvas.measure(label, DATA)
        _draw_tag_right(canvas, card, latency_left - t.TAG_STATUS_GAP, ping_y)
        canvas.text(label, (unit_right, ping_y), DATA, t.STATE_POOR, "rm")
        return

    color = TIER_COLORS[tier]
    unit_width = canvas.measure("ms", DATA)
    number = str(ping)
    number_right = unit_right - unit_width - LATENCY_UNIT_GAP
    latency_left = number_right - canvas.measure(number, DATA)
    _draw_tag_right(canvas, card, latency_left - t.TAG_STATUS_GAP, ping_y)
    canvas.text("ms", (unit_right, ping_y), DATA, color, "rm")
    canvas.text(number, (number_right, ping_y), DATA, color, "rm")

    players = node.get("players") if isinstance(node.get("players"), dict) else {}
    canvas.text(
        f"{players.get('online', 0)}/{players.get('max', 0)}",
        (right, players_y), DATA, t.INK, "rm",
    )
    version = canvas.fit(
        parse_minecraft_formatting(str(node.get("version") or "N/A"), t.INK_GHOST),
        VERSION,
        t.RAIL_WIDTH,
    )
    canvas.segments(version, (right, version_y), VERSION, "rm")


def _draw_spine(canvas: Canvas, card: CardLayout) -> None:
    if not card.children:
        return
    trunk_x = card.left + t.CHILD_INDENT / 2 - t.SPINE_DOT / 2
    last_child = card.children[-1]
    canvas.dotted_vline(
        trunk_x,
        card.bottom + t.CARD_GAP,
        last_child.icon_center_y,
        t.RULE,
    )
    for child in card.children:
        canvas.dotted_hline(child.icon_center_y, trunk_x, child.left, t.RULE)


def _draw_card(
    canvas: Canvas,
    card: CardLayout,
    group_default: str,
    icons: Dict[int, Optional[Image.Image]],
) -> None:
    online = bool(card.node.get("online"))
    resolved = _resolve_rendered_auth(card.node, group_default)
    address = get_server_display_address(card.node, pixel_font=True)
    _draw_card_shell(canvas, card, resolved, online)
    _draw_icon(canvas, icons.get(id(card.node)), card, online)
    _draw_motd_rows(canvas, card)
    _draw_meta_row(canvas, card, address, resolved)
    _draw_rail(canvas, card)


# ------------------------------------------------------------------------------
# 渲染入口
# ------------------------------------------------------------------------------


def _draw_empty_state(canvas: Canvas, top: float, bottom: float) -> None:
    center_y = (top + bottom) / 2
    canvas.text(
        "本群还没有配置服务器",
        (t.CANVAS_WIDTH / 2, center_y - 12), SUBTITLE, t.INK_FAINT, "mm",
    )
    canvas.text(
        "群管理员发送 /mcs edit 获取网页编辑链接",
        (t.CANVAS_WIDTH / 2, center_y + 12), ADDRESS, t.INK_GHOST, "mm",
    )


def _cleanup_old_images() -> None:
    try:
        now = time.time()
        for name in os.listdir(SAVE_IMG_DIR):
            if not name.startswith("mc_status_") or not name.endswith(".png"):
                continue
            path = os.path.join(SAVE_IMG_DIR, name)
            try:
                if now - os.path.getmtime(path) > RENDERED_IMAGE_TTL:
                    os.unlink(path)
            except OSError:
                continue
    except OSError:
        pass


def render_servers(
    display_data: Sequence[Dict[str, Any]],
    output_path: str,
    *,
    footer_text: str = "",
    source_label: str = "",
    group_default_auth: str = "",
    group_id: int = 0,
    icons: Optional[Dict[int, Optional[Image.Image]]] = None,
    settings: Optional[RenderSettings] = None,
) -> str:
    """同步渲染入口；生产与预览共用，不联网、不读群配置。"""
    settings = settings or current_settings()
    metrics = header_metrics(settings)
    cards, end_y = build_layout(list(display_data), metrics.list_top)
    list_height = max(0.0, end_y - metrics.list_top - (t.CARD_GAP if cards else 0))
    all_cards = list(_iter_cards(cards))
    legend_modes = _collect_auth_modes(all_cards, group_default_auth)
    stats = summarize(list(display_data))
    band = band_is_visible(settings, footer_text)

    prepared_icons = dict(icons or {})
    for card in all_cards:
        prepared_icons.setdefault(id(card.node), _builtin_icon(bool(card.node.get("online"))))

    height = calculate_image_height(
        metrics.list_top,
        list_height,
        footer_text,
        legend_modes,
        band,
        settings.min_height,
    )
    canvas = Canvas(t.CANVAS_WIDTH, height)
    canvas.tile_background(resolve_texture(settings, group_id))
    _draw_header(canvas, stats, source_label, metrics, settings)

    if cards:
        for card in all_cards:
            _draw_spine(canvas, card)
        for card in all_cards:
            _draw_card(canvas, card, group_default_auth, prepared_icons)
    else:
        reserved = band_height(footer_text) if band else 0
        _draw_empty_state(canvas, metrics.list_top, height - reserved)

    footer_height = band_height(footer_text) if band else 0
    cursor = height - footer_height
    if legend_modes:
        cursor -= t.SECTION_GAP + t.LEGEND_HEIGHT
        _draw_legend(canvas, legend_modes, cursor)
    if band:
        _draw_band(canvas, height, footer_text, settings)
    return canvas.save(output_path)


async def render_status_image(
    server_data_list: List[Dict[str, Any]],
    group_id: int,
    show_all_servers: bool,
    source_label: str = "",
) -> str:
    """准备数据和图标后在线程中渲染，返回带随机后缀的图片路径。"""
    clean_data = preprocess_server_data(server_data_list)
    display_data = prepare_data_for_display(clean_data, show_all_servers)
    nodes = list(_iter_nodes(display_data))

    icons: Dict[int, Optional[Image.Image]] = {}
    icon_results = await asyncio.gather(*(_load_icon(node) for node in nodes), return_exceptions=True)
    for node, result in zip(nodes, icon_results):
        icons[id(node)] = None if isinstance(result, Exception) else result

    _cleanup_old_images()
    output_path = os.path.join(SAVE_IMG_DIR, f"mc_status_{group_id}_{uuid.uuid4().hex[:8]}.png")
    return await asyncio.to_thread(
        render_servers,
        display_data,
        output_path,
        footer_text=get_footer(group_id),
        source_label=source_label or "",
        group_default_auth=get_group_default_auth_mode(group_id),
        group_id=group_id,
        icons=icons,
    )


__all__ = [
    "render_status_image",
    "render_servers",
    "build_layout",
    "calculate_image_height",
    "band_height",
    "band_is_visible",
    "header_metrics",
    "resolve_texture",
    "CardLayout",
    "HeaderMetrics",
]
