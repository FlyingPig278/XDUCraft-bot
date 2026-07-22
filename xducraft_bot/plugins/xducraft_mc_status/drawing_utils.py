from html.parser import HTMLParser
from typing import List, Tuple

from PIL import ImageColor, ImageDraw, ImageFont

from xducraft_bot.plugins.xducraft_mc_status.constants import HTML_COLOR_CODES, MINECRAFT_COLOR_CODES


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
    line_separator: str = " | ",
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


def _segments_length(segments: List[ColoredSegment], font: ImageFont.FreeTypeFont) -> float:
    return sum(font.getlength(segment_text) for segment_text, _ in segments)


def _draw_segments(
    draw: ImageDraw.ImageDraw,
    segments: List[ColoredSegment],
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    anchor: str,
) -> None:
    x, y = position
    horizontal_anchor = anchor[0] if anchor and anchor[0] in "lmr" else "l"
    vertical_anchor = anchor[1:] if anchor and len(anchor) > 1 else "a"
    total_length = sum(draw.textlength(segment_text, font=font) for segment_text, _ in segments)

    if horizontal_anchor == "r":
        x -= total_length
    elif horizontal_anchor == "m":
        x -= total_length / 2

    segment_anchor = f"l{vertical_anchor}"
    for segment_text, color in segments:
        draw.text((x, y), segment_text, fill=color, font=font, anchor=segment_anchor)
        x += draw.textlength(segment_text, font=font)


def draw_colored_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    default_color: Color = (255, 255, 255, 255),
    anchor: str = "lm",
) -> None:
    segments = parse_minecraft_formatting(text, default_color)
    _draw_segments(draw, segments, position, font, anchor)


def draw_colored_title_html(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    default_color: Color = (255, 255, 255, 255),
    anchor: str = "lm",
) -> None:
    segments = parse_minecraft_formatting(text, default_color, is_html=True)
    _draw_segments(draw, segments, position, font, anchor)


def calculate_clean_length(text: str, font: ImageFont.FreeTypeFont, is_html: bool) -> int:
    """计算去除 Minecraft/HTML 格式标记后的实际像素宽度。"""
    segments = parse_minecraft_formatting(text, is_html=is_html)
    return int(_segments_length(segments, font))


def _calculate_minecraft_length(text_with_mc_codes: str, font: ImageFont.FreeTypeFont) -> int:
    """兼容旧调用：计算只包含 Minecraft § 码的字符串宽度。"""
    segments = parse_minecraft_formatting(text_with_mc_codes)
    return int(_segments_length(segments, font))
