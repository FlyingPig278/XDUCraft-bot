"""MOTD 富文本解析与绘制。

Minecraft 的 MOTD 有三种写法要同时支持：legacy 的 ``§c`` 颜色码、
1.16+ 的 ``§x§R§R§G§G§B§B`` / ``§#RRGGBB`` 十六进制色，以及聚合 API 常见的
``<font color=...>`` HTML 片段。三者都会被解析成 ``(文本, 颜色)`` 分段，
再由 Pillow 逐段绘制。
"""

from __future__ import annotations

from html.parser import HTMLParser
from math import ceil
from typing import List, Optional, Sequence, Tuple

from PIL import ImageColor, ImageDraw, ImageFont

from .constants import HTML_COLOR_CODES, MINECRAFT_COLOR_CODES


Color = Tuple[int, int, int, int]
ColoredSegment = Tuple[str, Color]
LEGACY_COLOR_CODES = frozenset("0123456789abcdef")
LEGACY_FORMAT_CODES = frozenset("klmno")
LEGACY_HEX_DIGITS = frozenset("0123456789abcdef")


def _as_rgba(color) -> Color:
    """将 Pillow 支持的颜色值统一成 RGBA 元组。"""
    if isinstance(color, tuple):
        if len(color) == 4:
            return color
        if len(color) == 3:
            return color[0], color[1], color[2], 255
    return ImageColor.getcolor(str(color), "RGBA")


def _resolve_color(color_name: str, fallback: Color) -> Color:
    normalized_name = str(color_name).strip().lower()
    if normalized_name in HTML_COLOR_CODES:
        return _as_rgba(HTML_COLOR_CODES[normalized_name])
    try:
        return _as_rgba(ImageColor.getcolor(normalized_name, "RGBA"))
    except (TypeError, ValueError):
        return fallback


def _append_segment(segments: List[ColoredSegment], text: str, color: Color) -> None:
    if not text:
        return
    if segments and segments[-1][1] == color:
        previous_text, _ = segments[-1]
        segments[-1] = previous_text + text, color
    else:
        segments.append((text, color))


def _parse_legacy_text(
    text: str,
    initial_color: Color,
    reset_color: Color,
    segments: List[ColoredSegment],
) -> Color:
    """解析一段 § legacy 文本，并返回该段结束时的当前颜色。"""
    current_color = initial_color
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            _append_segment(segments, "".join(buffer), current_color)
            buffer.clear()

    index = 0
    while index < len(text):
        if text[index] != "§" or index + 1 >= len(text):
            buffer.append(text[index])
            index += 1
            continue

        code = text[index + 1].lower()

        # Java 1.16+ 生态常见的 legacy 十六进制形式：§x§R§R§G§G§B§B。
        if code == "x" and index + 13 < len(text):
            hex_pairs = text[index + 2:index + 14]
            if all(
                hex_pairs[offset] == "§" and hex_pairs[offset + 1].lower() in LEGACY_HEX_DIGITS
                for offset in range(0, 12, 2)
            ):
                flush()
                hex_value = "".join(hex_pairs[offset + 1] for offset in range(0, 12, 2))
                current_color = _resolve_color(f"#{hex_value}", reset_color)
                index += 14
                continue

        # Adventure 兼容形式：§#RRGGBB。
        if code == "#" and index + 7 < len(text):
            hex_value = text[index + 2:index + 8]
            if all(char.lower() in LEGACY_HEX_DIGITS for char in hex_value):
                flush()
                current_color = _resolve_color(f"#{hex_value}", reset_color)
                index += 8
                continue

        if code in LEGACY_COLOR_CODES:
            flush()
            current_color = _as_rgba(MINECRAFT_COLOR_CODES[code])
            index += 2
            continue

        if code == "r":
            flush()
            current_color = reset_color
            index += 2
            continue

        if code in LEGACY_FORMAT_CODES:
            # 当前图片字体没有对应的粗体/斜体等字形；至少正确消费格式码，
            # 避免把 §k-§o 当成可见文本。
            flush()
            index += 2
            continue

        # 未知代码不是 Minecraft 格式码，按普通文本保留，避免静默吞字。
        buffer.append(text[index])
        index += 1

    flush()
    return current_color


class _MinecraftHTMLParser(HTMLParser):
    """解析状态 API 常见的 <font color=...> MOTD 片段。"""

    def __init__(self, default_color: Color, line_separator: str):
        super().__init__(convert_charrefs=True)
        self.default_color = default_color
        self.current_color = default_color
        self.line_separator = line_separator
        self.color_stack: List[Color] = []
        self.segments: List[ColoredSegment] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "br":
            _append_segment(self.segments, self.line_separator, self.current_color)
            return
        if tag != "font":
            return

        self.color_stack.append(self.current_color)
        attributes = {str(name).lower(): value for name, value in attrs}
        color_name = attributes.get("color")
        if color_name:
            self.current_color = _resolve_color(color_name, self.default_color)

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag.lower() == "br":
            _append_segment(self.segments, self.line_separator, self.current_color)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "font" and self.color_stack:
            self.current_color = self.color_stack.pop()

    def handle_data(self, data: str) -> None:
        normalized_data = data.replace("\r\n", "\n").replace("\r", "\n").replace("\n", self.line_separator)
        self.current_color = _parse_legacy_text(
            normalized_data,
            initial_color=self.current_color,
            reset_color=self.default_color,
            segments=self.segments,
        )


def parse_minecraft_formatting(
    text: str,
    default_color: Color = (255, 255, 255, 255),
    *,
    is_html: bool = False,
    # 多行 MOTD 压成一行时的分隔符。Minecraft AE 的 U+00B7 字形映射异常，
    # 会被画成类似字母 ``u`` 的形状；U+2022 在这套字体里显示为正常圆点。
    line_separator: str = " • ",
) -> List[ColoredSegment]:
    """把 Minecraft legacy/HTML 文本解析成可供 Pillow 绘制的彩色分段。"""
    normalized_default = _as_rgba(default_color)
    normalized_text = str(text)

    if is_html:
        parser = _MinecraftHTMLParser(normalized_default, line_separator)
        parser.feed(normalized_text)
        parser.close()
        return parser.segments

    segments: List[ColoredSegment] = []
    normalized_text = normalized_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", line_separator)
    _parse_legacy_text(normalized_text, normalized_default, normalized_default, segments)
    return segments


def measure_segments(segments: Sequence[ColoredSegment], font: ImageFont.FreeTypeFont) -> float:
    """分段文本的总像素宽度。"""
    return sum(font.getlength(segment_text) for segment_text, _ in segments)


_segments_length = measure_segments  # 兼容旧名字


def truncate_segments(
    segments: Sequence[ColoredSegment],
    font: ImageFont.FreeTypeFont,
    max_width: float,
    ellipsis: str = "…",
) -> List[ColoredSegment]:
    """按**像素宽度**截断分段文本，保留每段自己的颜色。

    旧实现的做法是先按像素判断超长、再按字符数 ``text[:40]`` 截断——中英文
    混排时字符数和像素宽度完全不成比例，宽的会溢出到右侧信息列上，窄的又白白
    浪费空间。这里逐字符累加实际宽度，超了就停，并保证省略号也放得下。
    """
    if max_width <= 0:
        return []
    if measure_segments(segments, font) <= max_width:
        return list(segments)

    ellipsis_width = font.getlength(ellipsis)
    budget = max_width - ellipsis_width
    if budget <= 0:
        return [(ellipsis, segments[0][1] if segments else (255, 255, 255, 255))]

    truncated: List[ColoredSegment] = []
    used = 0.0
    last_color: Color = (255, 255, 255, 255)

    for segment_text, color in segments:
        last_color = color
        segment_width = font.getlength(segment_text)
        if used + segment_width <= budget:
            truncated.append((segment_text, color))
            used += segment_width
            continue

        kept = []
        for character in segment_text:
            character_width = font.getlength(character)
            if used + character_width > budget:
                break
            kept.append(character)
            used += character_width
        if kept:
            truncated.append(("".join(kept), color))
        break

    truncated.append((ellipsis, last_color))
    return truncated


def truncate_text(text: str, font: ImageFont.FreeTypeFont, max_width: float, ellipsis: str = "…") -> str:
    """按像素宽度截断纯文本。"""
    if font.getlength(text) <= max_width:
        return text
    segments = truncate_segments([(text, (255, 255, 255, 255))], font, max_width, ellipsis)
    return "".join(segment_text for segment_text, _ in segments)


def draw_segments(
    draw: ImageDraw.ImageDraw,
    segments: Sequence[ColoredSegment],
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    anchor: str = "lm",
) -> float:
    """逐段绘制彩色文本，返回绘制的总宽度。"""
    x, y = position
    horizontal_anchor = anchor[0] if anchor and anchor[0] in "lmr" else "l"
    vertical_anchor = anchor[1:] if anchor and len(anchor) > 1 else "a"
    total_length = measure_segments(segments, font)

    if horizontal_anchor == "r":
        x -= total_length
    elif horizontal_anchor == "m":
        x -= total_length / 2

    segment_anchor = f"l{vertical_anchor}"
    for segment_text, color in segments:
        draw.text((x, y), segment_text, fill=color, font=font, anchor=segment_anchor)
        x += font.getlength(segment_text)
    return total_length


_draw_segments = draw_segments  # 兼容旧名字


def draw_colored_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    default_color: Color = (255, 255, 255, 255),
    anchor: str = "lm",
    max_width: Optional[float] = None,
) -> float:
    """绘制含 ``§`` 颜色码的文本。``max_width`` 非空时按像素截断。"""
    segments = parse_minecraft_formatting(text, default_color)
    if max_width is not None:
        segments = truncate_segments(segments, font, max_width)
    return draw_segments(draw, segments, position, font, anchor)


def draw_colored_title_html(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    default_color: Color = (255, 255, 255, 255),
    anchor: str = "lm",
    max_width: Optional[float] = None,
) -> float:
    """绘制含 ``<font color=...>`` 的文本。``max_width`` 非空时按像素截断。"""
    segments = parse_minecraft_formatting(text, default_color, is_html=True)
    if max_width is not None:
        segments = truncate_segments(segments, font, max_width)
    return draw_segments(draw, segments, position, font, anchor)


def calculate_clean_length(text: str, font: ImageFont.FreeTypeFont, is_html: bool = False) -> int:
    """去掉格式标记后的实际像素宽度。"""
    return int(measure_segments(parse_minecraft_formatting(text, is_html=is_html), font))


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    """文本的 (宽, 高)，高度取字体的实际墨水高度。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(ceil(bbox[2] - bbox[0])), int(ceil(bbox[3] - bbox[1]))


def draw_pill(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    background: Color,
    foreground: Color,
    *,
    padding_x: int = 10,
    padding_y: int = 5,
    radius: int = 8,
    anchor: str = "lt",
    fixed_height: Optional[int] = None,
) -> Tuple[int, int]:
    """绘制一个圆角胶囊标签（Tag、验证方式徽章都用它）。

    Args:
        position: 依 ``anchor`` 解释。``lt`` = 左上角，``lm`` = 左侧垂直居中。
        fixed_height: 指定后忽略文字高度，保证同一行的多个胶囊等高。

    Returns:
        ``(宽, 高)``，方便调用方继续往右排版。
    """
    text_width, text_height = text_size(draw, text, font)
    width = text_width + 2 * padding_x
    height = fixed_height if fixed_height is not None else text_height + 2 * padding_y

    x, y = position
    if anchor[0] == "r":
        x -= width
    elif anchor[0] == "m":
        x -= width / 2
    if len(anchor) > 1 and anchor[1] == "m":
        y -= height / 2
    elif len(anchor) > 1 and anchor[1] == "b":
        y -= height

    draw.rounded_rectangle((x, y, x + width, y + height), radius=radius, fill=background)
    draw.text((x + width / 2, y + height / 2), text, font=font, fill=foreground, anchor="mm")
    return int(width), int(height)


def with_alpha(color: Color, alpha: int) -> Color:
    """替换颜色的 alpha 通道。"""
    red, green, blue = color[0], color[1], color[2]
    return red, green, blue, max(0, min(255, int(alpha)))


def blend(foreground: Color, background: Color, ratio: float) -> Color:
    """按比例混合两个颜色，``ratio`` 为 0 时得到 ``background``。"""
    ratio = max(0.0, min(1.0, ratio))
    return tuple(  # type: ignore[return-value]
        int(round(background[index] + (foreground[index] - background[index]) * ratio))
        for index in range(4)
    )
