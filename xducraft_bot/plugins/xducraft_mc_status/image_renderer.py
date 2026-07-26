"""把服务器状态渲染成图片。

结构上有一个关键改动：**布局和绘制分成两步**。

旧实现里 ``calculate_image_height`` 和 ``_recursive_draw_servers`` 各自用一套
算术推导 y 坐标，两边的规则必须手工保持一致——加一个“有玩家就多 35px”的分支
要改两处，漏掉一处画布就会被截断或者留一大片空白。现在先一次性算出每张卡片的
绝对坐标（:func:`build_layout`），高度直接由布局结果得出，绘制只管照着画。

同样的原因，父子连线也不再靠“上一行高度”反推，而是直接用父节点和子节点各自
已知的绝对坐标连线。
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from nonebot.log import logger
from PIL import Image, ImageColor, ImageDraw, ImageFile

from . import auth_mode as auth
from .constants import (
    AUTH_BADGE_PADDING_X, AUTH_BADGE_PADDING_Y, AUTH_BADGE_RADIUS, AUTH_BADGE_SPACING,
    AUTH_BADGE_UNCONFIRMED_ALPHA, CANVAS_BACKGROUND_COLOR, CARD_ACCENT_OFFLINE_COLOR,
    CARD_ACCENT_ONLINE_COLOR, CARD_ACCENT_WIDTH, CARD_BACKGROUND_COLOR,
    CARD_BACKGROUND_OFFLINE_COLOR, CARD_BORDER_COLOR, CARD_BORDER_OFFLINE_COLOR, CARD_GAP,
    CARD_HEIGHT, CARD_ICON_OFFSET_Y, CARD_PADDING_X, CARD_RADIUS, CARD_TEXT_OFFSET_X,
    CHILD_INDENT_PX, CONNECTOR_LINE_COLOR, CONNECTOR_LINE_THICKNESS, CREDIT_TEXT_COLOR,
    DEFAULT_SERVER_ICON_PATH, HEADER_BOTTOM_COLOR, HEADER_SUBTITLE_COLOR, HEADER_TOP_COLOR,
    IMAGE_WIDTH, LAYOUT_BASE_PADDING, LAYOUT_CREDIT_AREA_HEIGHT, LAYOUT_FOOTER_AREA_HEIGHT,
    LAYOUT_LEGEND_AREA_HEIGHT, LAYOUT_SERVER_ICON_SIZE, LAYOUT_TITLE_AREA_HEIGHT,
    MAIN_CONTENT_BACKGROUND_COLOR, MUTED_TEXT_COLOR, OFFLINE_SERVER_ICON_PATH,
    OFFLINE_TEXT_COLOR, OFFSET_IP_CENTER_Y, OFFSET_MOTD_CENTER_Y, OFFSET_PING_CENTER_Y,
    OFFSET_PLAYER_COUNT_CENTER_Y, OFFSET_PLAYER_LIST_CENTER_Y, OFFSET_SERVER_LIST_START_Y,
    OFFSET_VERSION_CENTER_Y, PING_COLOR_GREEN, PING_COLOR_RED, PING_COLOR_YELLOW,
    PING_THRESHOLD_FAIR, PING_THRESHOLD_GOOD, PLAYER_LIST_DOT_SPACING, PLAYER_ONLINE_DOT_COLOR,
    PLAYER_ROW_EXTRA_HEIGHT, PRIMARY_TEXT_COLOR, RENDERED_IMAGE_TTL,
    RIGHT_COLUMN_RESERVED_WIDTH, SAVE_IMG_DIR, SECONDARY_TEXT_COLOR, TAG_DEFAULT_BACKGROUND,
    TAG_PADDING_X, TAG_PADDING_Y, TAG_RADIUS, TAG_TEXT_BRIGHTNESS_THRESHOLD, TAG_TEXT_COLOR,
)
from .data_manager import get_footer, get_group_default_auth_mode
from .decode_image import decode_image
from .drawing_utils import (
    draw_colored_title, draw_pill, draw_segments, parse_minecraft_formatting,
    text_size, truncate_segments, truncate_text, with_alpha,
)
from .fonts import (
    FONT_MC_MEDIUM, FONT_MC_MOTD, FONT_MC_SMALL, FONT_MC_TITLE, FONT_ZH_BADGE,
    FONT_ZH_CREDIT, FONT_ZH_LEGEND, FONT_ZH_SUMMARY, FONT_ZH_TAG,
)
from .status_fetcher import has_player_list, prepare_data_for_display, preprocess_server_data, summarize

ImageFile.LOAD_TRUNCATED_IMAGES = True

CREDIT_TEXT = "Powered by FlyingPig278, LITTLE-UNIkeEN"
# favicon 官方只有 64×64；给到 2048×2048 已足够兼容非标准图标，同时能挡住
# 小体积、高分辨率的图片解压炸弹。
MAX_ICON_PIXELS = 2048 * 2048


# ==============================================================================
# 布局
# ==============================================================================

@dataclass
class CardLayout:
    """一张服务器卡片的绝对坐标。"""

    node: Dict[str, Any]
    level: int
    top: int
    height: int
    children: List["CardLayout"] = field(default_factory=list)

    @property
    def left(self) -> int:
        return LAYOUT_BASE_PADDING + self.level * CHILD_INDENT_PX

    @property
    def right(self) -> int:
        return IMAGE_WIDTH - LAYOUT_BASE_PADDING

    @property
    def icon_center_y(self) -> int:
        return self.top + CARD_ICON_OFFSET_Y + LAYOUT_SERVER_ICON_SIZE // 2

    @property
    def icon_bottom(self) -> int:
        return self.top + CARD_ICON_OFFSET_Y + LAYOUT_SERVER_ICON_SIZE


def build_layout(nodes: List[Dict[str, Any]], start_y: int, level: int = 0) -> Tuple[List[CardLayout], int]:
    """递归算出每张卡片的绝对坐标，返回 ``(卡片列表, 结束 y)``。"""
    cards: List[CardLayout] = []
    cursor = start_y

    for node in nodes:
        height = CARD_HEIGHT + (PLAYER_ROW_EXTRA_HEIGHT if has_player_list(node) else 0)
        card = CardLayout(node=node, level=level, top=cursor, height=height)
        cursor += height + CARD_GAP

        children = node.get("children") or []
        if children:
            card.children, cursor = build_layout(children, cursor, level + 1)

        cards.append(card)

    return cards, cursor


def _iter_cards(cards: List[CardLayout]):
    for card in cards:
        yield card
        if card.children:
            yield from _iter_cards(card.children)


def _collect_auth_modes(cards: List[CardLayout], group_default: str) -> List[str]:
    """图例里要展示哪些验证方式（按固定顺序，只列出实际出现过的）。"""
    present = set()
    for card in cards:
        resolved = auth.resolve_auth(card.node, group_default)
        if resolved.mode != auth.MODE_UNKNOWN:
            present.add(resolved.mode)
    order = (auth.MODE_OFFICIAL, auth.MODE_MUA, auth.MODE_YGGDRASIL, auth.MODE_OFFLINE, auth.MODE_MIXED)
    return [mode for mode in order if mode in present]


def calculate_image_height(list_height: int, footer_text: str, legend_modes: List[str]) -> int:
    """总高度 = 顶栏 + 列表 + 图例 + 页脚 + 署名。"""
    total = LAYOUT_TITLE_AREA_HEIGHT + OFFSET_SERVER_LIST_START_Y + list_height
    if legend_modes:
        total += LAYOUT_LEGEND_AREA_HEIGHT
    if footer_text:
        total += LAYOUT_FOOTER_AREA_HEIGHT
    total += LAYOUT_CREDIT_AREA_HEIGHT
    return max(total, LAYOUT_TITLE_AREA_HEIGHT + LAYOUT_CREDIT_AREA_HEIGHT + 80)


# ==============================================================================
# 背景与顶栏
# ==============================================================================

def _draw_vertical_gradient(
    image: Image.Image, box: Tuple[int, int, int, int],
    top_color: Tuple[int, int, int, int], bottom_color: Tuple[int, int, int, int],
) -> None:
    """在指定区域画一条竖直渐变。"""
    x0, y0, x1, y1 = box
    height = max(1, y1 - y0)
    gradient = Image.new("RGBA", (1, height))
    pixels = gradient.load()
    for offset in range(height):
        ratio = offset / max(1, height - 1)
        pixels[0, offset] = tuple(
            int(round(top_color[index] + (bottom_color[index] - top_color[index]) * ratio))
            for index in range(4)
        )
    image.paste(gradient.resize((x1 - x0, height)), (x0, y0))


def _draw_header(
    image: Image.Image, draw: ImageDraw.ImageDraw,
    stats: Dict[str, int], source_label: str,
) -> None:
    """顶栏：标题 + 概览。"""
    _draw_vertical_gradient(image, (0, 0, IMAGE_WIDTH, LAYOUT_TITLE_AREA_HEIGHT),
                            HEADER_TOP_COLOR, HEADER_BOTTOM_COLOR)

    draw.text((LAYOUT_BASE_PADDING, 54), "Minecraft 服务器状态",
              fill=PRIMARY_TEXT_COLOR, font=FONT_MC_TITLE, anchor="lm")

    subtitle = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据源 {source_label}"
    draw.text((LAYOUT_BASE_PADDING, 104), subtitle,
              fill=HEADER_SUBTITLE_COLOR, font=FONT_ZH_SUMMARY, anchor="lm")

    # 右侧概览：从右往左排，这样文字变长也不会顶到标题。
    chip_x = IMAGE_WIDTH - LAYOUT_BASE_PADDING
    chips = [
        (f"{stats['players_online']} 人在线", PLAYER_ONLINE_DOT_COLOR),
        (f"{stats['online']}/{stats['total']} 服务器在线",
         CARD_ACCENT_ONLINE_COLOR if stats["online"] else CARD_ACCENT_OFFLINE_COLOR),
    ]
    for text, accent in chips:
        width, _ = draw_pill(
            draw, text, (chip_x, 78), FONT_ZH_SUMMARY,
            background=(0, 0, 0, 90), foreground=accent,
            padding_x=16, padding_y=9, radius=16, anchor="rm",
        )
        chip_x -= width + 12


def _draw_legend(draw: ImageDraw.ImageDraw, modes: List[str], top: int) -> None:
    """底部图例：这张图里出现过的验证方式各是什么颜色。"""
    if not modes:
        return

    center_y = top + LAYOUT_LEGEND_AREA_HEIGHT // 2
    draw.text((LAYOUT_BASE_PADDING, center_y), "登录验证方式",
              fill=MUTED_TEXT_COLOR, font=FONT_ZH_LEGEND, anchor="lm")

    cursor = LAYOUT_BASE_PADDING + text_size(draw, "登录验证方式", FONT_ZH_LEGEND)[0] + 18
    for mode in modes:
        style = auth.style_for(mode)
        width, _ = draw_pill(
            draw, style.label, (cursor, center_y), FONT_ZH_LEGEND,
            background=style.color, foreground=style.text_color,
            padding_x=10, padding_y=5, radius=AUTH_BADGE_RADIUS, anchor="lm",
        )
        cursor += width + 10


def _draw_footer_and_credit(
    draw: ImageDraw.ImageDraw, image_height: int, footer_text: str, footer_top: Optional[int],
) -> None:
    if footer_text and footer_top is not None:
        draw.text((LAYOUT_BASE_PADDING, footer_top + LAYOUT_FOOTER_AREA_HEIGHT // 2),
                  truncate_text(footer_text, FONT_ZH_SUMMARY, IMAGE_WIDTH - 2 * LAYOUT_BASE_PADDING),
                  fill=SECONDARY_TEXT_COLOR, font=FONT_ZH_SUMMARY, anchor="lm")

    draw.text((IMAGE_WIDTH // 2, image_height - LAYOUT_CREDIT_AREA_HEIGHT // 2), CREDIT_TEXT,
              fill=CREDIT_TEXT_COLOR, font=FONT_ZH_CREDIT, anchor="mm")


# ==============================================================================
# 卡片
# ==============================================================================

def _resolve_tag_text_color(background_color: str) -> Tuple[int, int, int, int]:
    """按背景亮度在白字/黑字之间切换，保证浅色 Tag 也读得清。"""
    try:
        red, green, blue, _ = ImageColor.getcolor(background_color, "RGBA")
    except ValueError:
        # Pillow 不解析 CSS 的小数 alpha（rgba(..., 0.6)），但 Web UI 导出的
        # tag_color 可能是这种写法；亮度只看前三个通道即可。
        text = str(background_color).strip().lower()
        if not (text.startswith("rgba(") and text.endswith(")")):
            return TAG_TEXT_COLOR
        try:
            channels = [part.strip() for part in text[5:-1].split(",")]
            if len(channels) != 4:
                return TAG_TEXT_COLOR
            red, green, blue = (int(channels[index]) for index in range(3))
            if any(channel < 0 or channel > 255 for channel in (red, green, blue)):
                return TAG_TEXT_COLOR
            alpha = float(channels[3])
            if alpha < 0 or alpha > 1:
                return TAG_TEXT_COLOR
        except (TypeError, ValueError):
            return TAG_TEXT_COLOR

    brightness = (0.299 * red) + (0.587 * green) + (0.114 * blue)
    if brightness >= TAG_TEXT_BRIGHTNESS_THRESHOLD:
        return 0, 0, 0, TAG_TEXT_COLOR[3] if len(TAG_TEXT_COLOR) > 3 else 255
    return TAG_TEXT_COLOR


def _ping_color(ping: int) -> Tuple[int, int, int, int]:
    if ping < PING_THRESHOLD_GOOD:
        return PING_COLOR_GREEN
    if ping < PING_THRESHOLD_FAIR:
        return PING_COLOR_YELLOW
    return PING_COLOR_RED


def _draw_card_background(draw: ImageDraw.ImageDraw, card: CardLayout, is_online: bool) -> None:
    box = (card.left, card.top, card.right, card.top + card.height)
    draw.rounded_rectangle(
        box, radius=CARD_RADIUS,
        fill=CARD_BACKGROUND_COLOR if is_online else CARD_BACKGROUND_OFFLINE_COLOR,
        outline=CARD_BORDER_COLOR if is_online else CARD_BORDER_OFFLINE_COLOR,
        width=1,
    )
    # 左侧状态条：贴着圆角内侧画一个窄条，在线绿、离线灰红。
    accent = CARD_ACCENT_ONLINE_COLOR if is_online else CARD_ACCENT_OFFLINE_COLOR
    draw.rounded_rectangle(
        (card.left, card.top + 1, card.left + CARD_ACCENT_WIDTH + CARD_RADIUS, card.top + card.height - 1),
        radius=CARD_RADIUS, fill=accent,
    )
    draw.rectangle(
        (card.left + CARD_ACCENT_WIDTH, card.top + 1,
         card.left + CARD_ACCENT_WIDTH + CARD_RADIUS, card.top + card.height - 1),
        fill=CARD_BACKGROUND_COLOR if is_online else CARD_BACKGROUND_OFFLINE_COLOR,
    )


async def _load_icon(server_data: Dict[str, Any]) -> Optional[Image.Image]:
    """取服务器图标：优先 favicon，否则按在线状态用内置图标。"""
    favicon = server_data.get("favicon")
    if favicon:
        try:
            icon_bytes = await decode_image(favicon)
            if icon_bytes:
                with Image.open(icon_bytes) as raw:
                    if raw.width <= 0 or raw.height <= 0 or raw.width * raw.height > MAX_ICON_PIXELS:
                        logger.debug(
                            "[MCStatus] favicon 尺寸异常 {}x{}: {}",
                            raw.width, raw.height, server_data.get("ip"),
                        )
                        raise ValueError("favicon 像素数超过上限")
                    return raw.convert("RGBA").resize(
                        (LAYOUT_SERVER_ICON_SIZE, LAYOUT_SERVER_ICON_SIZE), Image.Resampling.LANCZOS
                    )
        except Exception as exc:
            logger.debug("[MCStatus] favicon 解码失败 {}: {}", server_data.get("ip"), exc)

    path = DEFAULT_SERVER_ICON_PATH if server_data.get("online") else OFFLINE_SERVER_ICON_PATH
    try:
        with Image.open(path) as raw:
            return raw.convert("RGBA").resize(
                (LAYOUT_SERVER_ICON_SIZE, LAYOUT_SERVER_ICON_SIZE), Image.Resampling.LANCZOS
            )
    except Exception as exc:
        logger.warning("[MCStatus] 内置图标加载失败 {}: {}", path, exc)
        return None


def _paste_icon(image: Image.Image, icon: Optional[Image.Image], card: CardLayout, is_online: bool) -> None:
    if icon is None:
        return
    if not is_online:
        # 离线服务器的图标压暗，让在线的一眼更突出。
        icon = Image.blend(Image.new("RGBA", icon.size, (0, 0, 0, 0)), icon, 0.45)
    image.paste(icon, (card.left + CARD_PADDING_X, card.top + CARD_ICON_OFFSET_Y), icon)


def _draw_tag(draw: ImageDraw.ImageDraw, card: CardLayout, tag: str, tag_color: str) -> int:
    """画 Tag 胶囊，返回它占用的宽度（含右侧间距）；没有 Tag 时返回 0。"""
    if not tag:
        return 0

    background = f"#{tag_color}" if tag_color and not str(tag_color).startswith("#") else (tag_color or TAG_DEFAULT_BACKGROUND)
    try:
        ImageColor.getcolor(str(background), "RGBA")
    except ValueError:
        background = TAG_DEFAULT_BACKGROUND

    width, _ = draw_pill(
        draw, tag,
        (card.left + CARD_TEXT_OFFSET_X, card.top + OFFSET_MOTD_CENTER_Y),
        FONT_ZH_TAG,
        background=background, foreground=_resolve_tag_text_color(str(background)),
        padding_x=TAG_PADDING_X, padding_y=TAG_PADDING_Y, radius=TAG_RADIUS, anchor="lm",
    )
    return width + 14


def _motd_segments(server_data: Dict[str, Any]) -> Tuple[List[Tuple[str, Tuple[int, int, int, int]]], bool]:
    """把 MOTD 解析成彩色分段。返回 ``(分段, 是否是占位文本)``。"""
    description = server_data.get("description")
    comment = str(server_data.get("comment") or "")

    if isinstance(description, dict):
        html = description.get("html")
        raw = html or description.get("text") or ""
        raw = str(raw).replace("服务器已离线...", "").strip()
        # 默认 MOTD 没有信息量，有备注就用备注替掉。
        if raw in ("", "A Minecraft Server") and comment:
            return parse_minecraft_formatting(comment, SECONDARY_TEXT_COLOR), True
        if raw:
            return parse_minecraft_formatting(raw, PRIMARY_TEXT_COLOR, is_html=bool(html)), False
    elif isinstance(description, str) and description.strip():
        return parse_minecraft_formatting(description, PRIMARY_TEXT_COLOR), False

    if comment:
        return parse_minecraft_formatting(comment, SECONDARY_TEXT_COLOR), True
    return parse_minecraft_formatting("未获取到 MOTD", MUTED_TEXT_COLOR), True


def _draw_motd(draw: ImageDraw.ImageDraw, card: CardLayout, tag_width: int) -> None:
    server_data = card.node
    start_x = card.left + CARD_TEXT_OFFSET_X + tag_width
    center_y = card.top + OFFSET_MOTD_CENTER_Y
    max_width = card.right - RIGHT_COLUMN_RESERVED_WIDTH - start_x

    if not server_data.get("online"):
        text = str(server_data.get("comment") or "") or "服务器离线"
        draw.text((start_x, center_y), truncate_text(text, FONT_MC_MOTD, max_width),
                  fill=OFFLINE_TEXT_COLOR, font=FONT_MC_MOTD, anchor="lm")
        return

    # 多行 MOTD 已经在解析阶段被压成一行（用圆点分隔），这里只需按像素截断。
    segments, _ = _motd_segments(server_data)
    segments = truncate_segments(segments, FONT_MC_MOTD, max_width)
    draw_segments(draw, segments, (start_x, center_y), FONT_MC_MOTD, anchor="lm")


def _draw_address_and_auth(draw: ImageDraw.ImageDraw, card: CardLayout, group_default: str) -> None:
    """第二行：地址 + 登录验证方式徽章。"""
    server_data = card.node
    start_x = card.left + CARD_TEXT_OFFSET_X
    center_y = card.top + OFFSET_IP_CENTER_Y

    if server_data.get("hide_ip"):
        address = str(server_data.get("display_name") or "") or "[IP 已隐藏]"
    else:
        address = str(server_data.get("ip") or "未知服务器")

    resolved = auth.resolve_auth(server_data, group_default)
    badge_text = resolved.style.short_label if resolved.mode != auth.MODE_UNKNOWN else ""
    badge_width = 0
    if badge_text:
        badge_width = text_size(draw, badge_text, FONT_ZH_BADGE)[0] + 2 * AUTH_BADGE_PADDING_X + AUTH_BADGE_SPACING

    max_address_width = card.right - RIGHT_COLUMN_RESERVED_WIDTH - start_x - badge_width
    draw.text((start_x, center_y), truncate_text(address, FONT_MC_MEDIUM, max_address_width),
              fill=SECONDARY_TEXT_COLOR, font=FONT_MC_MEDIUM, anchor="lm")

    if not badge_text:
        return

    badge_x = start_x + min(FONT_MC_MEDIUM.getlength(address), max_address_width) + AUTH_BADGE_SPACING
    style = resolved.style
    # 实测确认的徽章用实色，仅按配置显示的降低不透明度——一眼看出哪些是“查出来的”。
    background = style.color if resolved.confirmed else with_alpha(style.color, AUTH_BADGE_UNCONFIRMED_ALPHA)
    draw_pill(
        draw, badge_text, (badge_x, center_y), FONT_ZH_BADGE,
        background=background, foreground=style.text_color,
        padding_x=AUTH_BADGE_PADDING_X, padding_y=AUTH_BADGE_PADDING_Y,
        radius=AUTH_BADGE_RADIUS, anchor="lm",
    )


def _draw_right_column(draw: ImageDraw.ImageDraw, card: CardLayout) -> None:
    """右侧：延迟 / 人数 / 版本。"""
    server_data = card.node
    right_x = card.right - CARD_PADDING_X

    if not server_data.get("online"):
        draw.text((right_x, card.top + OFFSET_PING_CENTER_Y), "OFFLINE",
                  fill=PING_COLOR_RED, font=FONT_MC_MEDIUM, anchor="rm")
        error = str(server_data.get("error") or "")
        if error:
            draw.text((right_x, card.top + OFFSET_PLAYER_COUNT_CENTER_Y),
                      truncate_text("连接失败", FONT_MC_MEDIUM, RIGHT_COLUMN_RESERVED_WIDTH),
                      fill=MUTED_TEXT_COLOR, font=FONT_MC_MEDIUM, anchor="rm")
        return

    ping = int(server_data.get("ping") or 0)
    draw.text((right_x, card.top + OFFSET_PING_CENTER_Y), f"{ping}ms",
              fill=_ping_color(ping), font=FONT_MC_MEDIUM, anchor="rm")

    players = server_data.get("players") if isinstance(server_data.get("players"), dict) else {}
    draw.text((right_x, card.top + OFFSET_PLAYER_COUNT_CENTER_Y),
              f"{players.get('online', 0)}/{players.get('max', 0)}",
              fill=SECONDARY_TEXT_COLOR, font=FONT_MC_MEDIUM, anchor="rm")

    draw_colored_title(
        draw, str(server_data.get("version") or "N/A"),
        (right_x, card.top + OFFSET_VERSION_CENTER_Y),
        font=FONT_MC_MEDIUM, default_color=MUTED_TEXT_COLOR, anchor="rm",
        max_width=RIGHT_COLUMN_RESERVED_WIDTH,
    )


def _draw_player_list(draw: ImageDraw.ImageDraw, card: CardLayout) -> None:
    """展开的“正在游玩”行。"""
    if not has_player_list(card.node):
        return

    players = card.node.get("players") or {}
    names = [str(player.get("name", "")) for player in players.get("sample", []) if player.get("name")]
    if not names:
        return

    right_x = card.right - CARD_PADDING_X
    center_y = card.top + OFFSET_PLAYER_LIST_CENTER_Y

    draw.text((right_x, center_y), "●", fill=PLAYER_ONLINE_DOT_COLOR, font=FONT_MC_SMALL, anchor="rm")
    dot_width = FONT_MC_SMALL.getlength("●") + PLAYER_LIST_DOT_SPACING

    suffix = " 正在游玩"
    available = (right_x - dot_width) - (card.left + CARD_TEXT_OFFSET_X) - FONT_MC_SMALL.getlength(suffix)
    # 按像素截断名字列表，而不是按字符数——中英文混排时两者差得很远。
    text = truncate_text(", ".join(names), FONT_MC_SMALL, max(0, available)) + suffix

    draw.text((right_x - dot_width, center_y), text,
              fill=SECONDARY_TEXT_COLOR, font=FONT_MC_SMALL, anchor="rm")


def _draw_connectors(draw: ImageDraw.ImageDraw, card: CardLayout) -> None:
    """父子连线。直接用双方已知的绝对坐标，不做任何高度反推。"""
    if not card.children:
        return

    trunk_x = card.left + CARD_PADDING_X + LAYOUT_SERVER_ICON_SIZE // 2
    last_child = card.children[-1]

    draw.line(
        (trunk_x, card.icon_bottom, trunk_x, last_child.icon_center_y),
        fill=CONNECTOR_LINE_COLOR, width=CONNECTOR_LINE_THICKNESS,
    )
    for child in card.children:
        draw.line(
            (trunk_x, child.icon_center_y, child.left, child.icon_center_y),
            fill=CONNECTOR_LINE_COLOR, width=CONNECTOR_LINE_THICKNESS,
        )


# ==============================================================================
# 渲染入口
# ==============================================================================

def _cleanup_old_images() -> None:
    """删掉过期的渲染结果，避免 data/images 无限增长。"""
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


def _render_sync(
    cards: List[CardLayout], list_height: int, footer_text: str,
    legend_modes: List[str], stats: Dict[str, int], source_label: str,
    group_default_auth: str, icons: Dict[int, Optional[Image.Image]],
    output_path: str,
) -> str:
    """真正的绘制。纯 CPU 工作，由调用方放到线程里执行。"""
    image_height = calculate_image_height(list_height, footer_text, legend_modes)
    image = Image.new("RGBA", (IMAGE_WIDTH, image_height), color=CANVAS_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)

    content_top = LAYOUT_TITLE_AREA_HEIGHT
    content_bottom = image_height - LAYOUT_CREDIT_AREA_HEIGHT
    if footer_text:
        content_bottom -= LAYOUT_FOOTER_AREA_HEIGHT
    legend_top = None
    if legend_modes:
        content_bottom -= LAYOUT_LEGEND_AREA_HEIGHT
        legend_top = content_bottom

    draw.rectangle((0, content_top, IMAGE_WIDTH, content_bottom), fill=MAIN_CONTENT_BACKGROUND_COLOR)
    _draw_header(image, draw, stats, source_label)

    # 连线画在卡片之前，避免线头压在卡片圆角上。
    for card in _iter_cards(cards):
        _draw_connectors(draw, card)

    for card in _iter_cards(cards):
        is_online = bool(card.node.get("online"))
        _draw_card_background(draw, card, is_online)
        _paste_icon(image, icons.get(id(card.node)), card, is_online)
        tag_width = _draw_tag(draw, card, str(card.node.get("tag") or ""), str(card.node.get("tag_color") or ""))
        _draw_motd(draw, card, tag_width)
        _draw_address_and_auth(draw, card, group_default_auth)
        _draw_right_column(draw, card)
        _draw_player_list(draw, card)

    if legend_modes and legend_top is not None:
        _draw_legend(draw, legend_modes, legend_top)

    footer_top = content_bottom + (LAYOUT_LEGEND_AREA_HEIGHT if legend_modes else 0) if footer_text else None
    _draw_footer_and_credit(draw, image_height, footer_text, footer_top)

    os.makedirs(SAVE_IMG_DIR, exist_ok=True)
    image.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path


async def render_status_image(
    server_data_list: List[Dict[str, Any]],
    group_id: int,
    show_all_servers: bool,
    source_label: str = "",
) -> str:
    """渲染状态图，返回生成的文件路径。

    文件名带随机后缀：同一个群里两条 ``/mcs`` 并发时，旧实现会写同一个
    ``mc_status_<群号>.png``，先完成的那张图可能在发送前就被后完成的覆盖掉，
    导致两个人都收到同一张（错误的）图。
    """
    clean_data = preprocess_server_data(server_data_list)
    display_data = prepare_data_for_display(clean_data, show_all_servers)

    cards, end_y = build_layout(display_data, LAYOUT_TITLE_AREA_HEIGHT + OFFSET_SERVER_LIST_START_Y)
    list_height = max(0, end_y - (LAYOUT_TITLE_AREA_HEIGHT + OFFSET_SERVER_LIST_START_Y))

    footer_text = get_footer(group_id)
    group_default_auth = get_group_default_auth_mode(group_id)
    all_cards = list(_iter_cards(cards))
    legend_modes = _collect_auth_modes(all_cards, group_default_auth)
    stats = summarize(display_data)

    # 图标下载是 IO，必须在进线程之前做完；用 id() 作键避免要求节点可哈希。
    icons: Dict[int, Optional[Image.Image]] = {}
    icon_results = await asyncio.gather(
        *(_load_icon(card.node) for card in all_cards), return_exceptions=True
    )
    for card, result in zip(all_cards, icon_results):
        icons[id(card.node)] = None if isinstance(result, Exception) else result

    _cleanup_old_images()
    output_path = os.path.join(SAVE_IMG_DIR, f"mc_status_{group_id}_{uuid.uuid4().hex[:8]}.png")

    # Pillow 绘制是纯 CPU 且相当慢（几十毫秒到几百毫秒），直接在事件循环里跑
    # 会卡住机器人对其他消息的响应。
    return await asyncio.to_thread(
        _render_sync, cards, list_height, footer_text, legend_modes,
        stats, source_label or "-", group_default_auth, icons, output_path,
    )


__all__ = ["render_status_image", "build_layout", "calculate_image_height", "CardLayout"]
