"""MOTD 富文本：解析、度量、折行。

三种写法要同时支持：legacy 的 ``§c`` 颜色码、1.16+ 的 ``§x§R§R§G§G§B§B`` /
``§#RRGGBB`` 十六进制色，以及聚合 API 常见的 ``<font color=...>`` HTML 片段。

相比旧实现有两处实质变化：

1. **格式码不再被丢掉。** ``§k``–``§o``（乱码/粗体/删除线/下划线/斜体）以前只是
   被“正确消费”然后扔掉，等于每个装饰过的 MOTD 都被降级成纯色文本。现在它们
   进入 :class:`Segment` 的样式位，由 :mod:`.raster` 真的画出来。
2. **换行不再丢内容。** 旧实现把 ``\\n`` 换成一个 ``■`` 记号挤进单行，再按字符数
   截断，一半内容直接消失。现在解析阶段完整保留换行，由 :func:`wrap_segments`
   按像素宽度排进两行 MOTD。

绘制在 :mod:`.raster`，这里只做与画布无关的纯计算。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from html.parser import HTMLParser
from typing import List, Optional, Sequence, Tuple

from PIL import ImageColor

from .fonts import FontSet, remap
from .constants import HTML_COLOR_CODES, MINECRAFT_COLOR_CODES

Color = Tuple[int, int, int, int]

LEGACY_COLOR_CODES = frozenset("0123456789abcdef")
LEGACY_HEX_DIGITS = frozenset("0123456789abcdef")

#: ``§`` 格式码 -> :class:`Segment` 上的样式字段。
LEGACY_FORMAT_CODES = {
    "k": "obfuscated",
    "l": "bold",
    "m": "strikethrough",
    "n": "underline",
    "o": "italic",
}


@dataclass(frozen=True)
class Segment:
    """一段样式一致的文本。"""

    text: str
    color: Color
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    obfuscated: bool = False
    #: MiniMessage 风格的渐变色标（至少两个）；非空时覆盖 ``color``。
    gradient: Optional[Tuple[Color, ...]] = None

    @property
    def styled(self) -> bool:
        return bool(
            self.bold or self.italic or self.underline
            or self.strikethrough or self.obfuscated or self.gradient
        )


@dataclass
class _Style:
    """解析过程中的当前样式。"""

    color: Color
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    obfuscated: bool = False
    gradient: Optional[Tuple[Color, ...]] = None

    def reset(self, color: Color) -> None:
        self.color = color
        self.bold = self.italic = self.underline = False
        self.strikethrough = self.obfuscated = False
        self.gradient = None

    def emit(self, text: str) -> Segment:
        return Segment(
            text=text, color=self.color, bold=self.bold, italic=self.italic,
            underline=self.underline, strikethrough=self.strikethrough,
            obfuscated=self.obfuscated, gradient=self.gradient,
        )

    def same_style(self, segment: Segment) -> bool:
        return (
            segment.color == self.color and segment.bold == self.bold
            and segment.italic == self.italic and segment.underline == self.underline
            and segment.strikethrough == self.strikethrough
            and segment.obfuscated == self.obfuscated and segment.gradient == self.gradient
        )


# ==============================================================================
# 颜色
# ==============================================================================

def as_rgba(color) -> Color:
    """把 Pillow 支持的颜色值统一成 RGBA 元组。"""
    if isinstance(color, tuple):
        if len(color) == 4:
            return color
        if len(color) == 3:
            return color[0], color[1], color[2], 255
    return ImageColor.getcolor(str(color), "RGBA")


def with_alpha(color: Color, alpha: int) -> Color:
    """替换颜色的不透明度。"""
    red, green, blue = as_rgba(color)[:3]
    return red, green, blue, max(0, min(255, int(alpha)))


def scale_alpha(color: Color, factor: float) -> Color:
    """按比例衰减不透明度。"""
    return with_alpha(color, int(round(as_rgba(color)[3] * factor)))


def resolve_color(color_name: str, fallback: Color) -> Color:
    normalized = str(color_name).strip().lower()
    if normalized in HTML_COLOR_CODES:
        return as_rgba(HTML_COLOR_CODES[normalized])
    try:
        return as_rgba(ImageColor.getcolor(normalized, "RGBA"))
    except (TypeError, ValueError):
        return fallback


def _linearize(channel: int) -> float:
    """sRGB 通道值去伽马，换算成线性光强。"""
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: Color) -> float:
    """WCAG 2.x 的相对亮度。

    不能直接对 sRGB 数值加权（旧实现用的 ``0.299R+0.587G+0.114B``）：那套系数是
    给**已经带伽马**的分量用的经验公式，绿色权重偏低，浅绿一类颜色会被算得太暗。
    实测就是这么翻车的——亮绿 ``#55FF55`` 算出来 184.8，刚好卡在 186 的阈值下面，
    于是拿到了白字，而同样刺眼的黄色 ``#FFFF55`` 拿到黑字。
    """
    red, green, blue = as_rgba(color)[:3]
    return (
        0.2126 * _linearize(red)
        + 0.7152 * _linearize(green)
        + 0.0722 * _linearize(blue)
    )


def contrast_ratio(foreground: Color, background: Color) -> float:
    """WCAG 2.x 对比度，范围 1（同色）到 21（纯黑对纯白）。"""
    first, second = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


# ==============================================================================
# 解析
# ==============================================================================

def _append(segments: List[Segment], text: str, style: _Style) -> None:
    if not text:
        return
    if segments and style.same_style(segments[-1]):
        segments[-1] = replace(segments[-1], text=segments[-1].text + text)
    else:
        segments.append(style.emit(text))


def _parse_legacy(text: str, style: _Style, reset_color: Color, segments: List[Segment]) -> None:
    """解析一段 ``§`` 文本，就地更新 ``style``。"""
    buffer: List[str] = []

    def flush() -> None:
        if buffer:
            _append(segments, "".join(buffer), style)
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
            pairs = text[index + 2:index + 14]
            if all(
                pairs[offset] == "§" and pairs[offset + 1].lower() in LEGACY_HEX_DIGITS
                for offset in range(0, 12, 2)
            ):
                flush()
                value = "".join(pairs[offset + 1] for offset in range(0, 12, 2))
                style.color = resolve_color(f"#{value}", reset_color)
                style.gradient = None
                index += 14
                continue

        # Adventure 兼容形式：§#RRGGBB。
        if code == "#" and index + 7 < len(text):
            value = text[index + 2:index + 8]
            if all(char.lower() in LEGACY_HEX_DIGITS for char in value):
                flush()
                style.color = resolve_color(f"#{value}", reset_color)
                style.gradient = None
                index += 8
                continue

        if code in LEGACY_COLOR_CODES:
            flush()
            # 原版规则：颜色码同时清空所有格式位。
            style.reset(as_rgba(MINECRAFT_COLOR_CODES[code]))
            index += 2
            continue

        if code == "r":
            flush()
            style.reset(reset_color)
            index += 2
            continue

        if code in LEGACY_FORMAT_CODES:
            flush()
            setattr(style, LEGACY_FORMAT_CODES[code], True)
            index += 2
            continue

        # 未知代码不是格式码，按普通文本保留，避免静默吞字。
        buffer.append(text[index])
        index += 1

    flush()


#: HTML 标签 -> 样式字段。状态 API 与 MiniMessage 转译器都会吐这些。
_HTML_STYLE_TAGS = {
    "b": "bold", "strong": "bold",
    "i": "italic", "em": "italic",
    "u": "underline", "ins": "underline",
    "s": "strikethrough", "strike": "strikethrough", "del": "strikethrough",
    "obf": "obfuscated", "obfuscated": "obfuscated",
}


class _MinecraftHTMLParser(HTMLParser):
    """解析状态 API 常见的 ``<font color=...>`` MOTD 片段。"""

    def __init__(self, default_color: Color):
        super().__init__(convert_charrefs=True)
        self.default_color = default_color
        self.style = _Style(color=default_color)
        self.stack: List[_Style] = []
        self.segments: List[Segment] = []

    def _push(self) -> None:
        self.stack.append(replace(self.style))

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "br":
            _append(self.segments, "\n", self.style)
            return

        if tag in _HTML_STYLE_TAGS:
            self._push()
            setattr(self.style, _HTML_STYLE_TAGS[tag], True)
            return

        if tag == "font":
            self._push()
            attributes = {str(name).lower(): value for name, value in attrs}
            color_name = attributes.get("color")
            if color_name:
                self.style.color = resolve_color(color_name, self.default_color)
                self.style.gradient = None
            return

        # MiniMessage 的 <gradient:#a:#b:#c...>。参考项目只认两个色标，这里放开到
        # 任意多个——彩虹名字是常见玩法，两个色标做不出彩虹。
        if tag.startswith("gradient"):
            self._push()
            stops = tuple(
                resolve_color(part, self.style.color) for part in tag.split(":")[1:] if part
            )
            if len(stops) >= 2:
                self.style.gradient = stops

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag.lower() == "br":
            _append(self.segments, "\n", self.style)
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if (tag in _HTML_STYLE_TAGS or tag == "font" or tag.startswith("gradient")) and self.stack:
            self.style = self.stack.pop()

    def handle_data(self, data: str) -> None:
        normalized = data.replace("\r\n", "\n").replace("\r", "\n")
        _parse_legacy(normalized, self.style, self.default_color, self.segments)


def parse_minecraft_formatting(
    text: str,
    default_color: Color = (255, 255, 255, 255),
    *,
    is_html: bool = False,
) -> List[Segment]:
    """把 Minecraft legacy/HTML 文本解析成带样式的分段。换行保留为 ``\\n``。"""
    normalized_default = as_rgba(default_color)
    normalized_text = str(text).replace("\r\n", "\n").replace("\r", "\n")

    if is_html:
        parser = _MinecraftHTMLParser(normalized_default)
        parser.feed(normalized_text)
        parser.close()
        return parser.segments

    segments: List[Segment] = []
    _parse_legacy(normalized_text, _Style(color=normalized_default), normalized_default, segments)
    return segments


# ==============================================================================
# 度量
# ==============================================================================

@lru_cache(maxsize=4096)
def is_full_width(font_set: FontSet, character: str) -> bool:
    """是不是全角字形（中日韩、全角标点）。"""
    return font_set.char_length(character) >= font_set.size * 0.9


def bold_offset(font_set: FontSet) -> int:
    """半角字的粗体重描偏移。

    原版渲染器的“粗体”就是把字再画一遍、右移 1 个游戏像素。半角字形画在 8×8 的
    设计网格上，所以 1 个游戏像素 = 字号 / 8。
    """
    return max(1, int(font_set.size) // 8)


def bold_offset_for(font_set: FontSet, character: str) -> int:
    """某个字的粗体偏移。全角字要减半。

    全角字形画在 16×16 的网格上（实测：32px 时半角 advance 24、全角 32），
    1 个游戏像素只有半角的一半。照半角的偏移去重描，中文会糊成一团——
    32px 下偏移 4px 几乎等于把笔画整体加粗一倍，“粗体渐变”会直接看不清。
    """
    if is_full_width(font_set, character):
        return max(1, int(font_set.size) // 16)
    return bold_offset(font_set)


def bold_width(text: str, font_set: FontSet) -> float:
    """一段文本因为粗体而多出来的宽度。"""
    return sum(bold_offset_for(font_set, character) for character in remap(text))


def measure_segments(segments: Sequence[Segment], font_set: FontSet) -> float:
    """分段文本的总像素宽度（计入粗体加宽）。

    粗体加宽必须按 **重映射之后** 的字算——绘制走的是 :meth:`FontSet.split`，
    它会先把画错的 Latin-1 标点换掉（``©`` 变成三个字符）。两边不一致的话，
    右对齐的文本就会偏出去。
    """
    return sum(
        font_set.length(segment.text)
        + (bold_width(segment.text, font_set) if segment.bold else 0)
        for segment in segments
    )


def segment_char_width(segment: Segment, character: str, font_set: FontSet) -> float:
    width = font_set.char_length(character)
    if segment.bold:
        width += bold_width(character, font_set)
    return width


def measure_text(text: str, font_set: FontSet) -> float:
    return font_set.length(text)


def truncate_segments(
    segments: Sequence[Segment],
    font_set: FontSet,
    max_width: float,
    ellipsis: str = "…",
) -> List[Segment]:
    """按像素宽度截断分段文本，保留每段自己的样式。"""
    if max_width <= 0:
        return []
    if measure_segments(segments, font_set) <= max_width:
        return list(segments)

    ellipsis_width = font_set.length(ellipsis)
    budget = max_width - ellipsis_width
    if budget <= 0:
        tail = segments[0] if segments else Segment("", (255, 255, 255, 255))
        return [replace(tail, text=ellipsis, bold=False, obfuscated=False, gradient=None)]

    kept: List[Segment] = []
    used = 0.0
    last = Segment("", (255, 255, 255, 255))

    for segment in segments:
        last = segment
        width = font_set.length(segment.text)
        if segment.bold:
            width += bold_offset(font_set) * len(segment.text)
        if used + width <= budget:
            kept.append(segment)
            used += width
            continue

        buffer: List[str] = []
        for character in segment.text:
            char_width = segment_char_width(segment, character, font_set)
            if used + char_width > budget:
                break
            buffer.append(character)
            used += char_width
        if buffer:
            kept.append(replace(segment, text="".join(buffer)))
        break

    kept.append(replace(last, text=ellipsis, bold=False, obfuscated=False, gradient=None))
    return kept


def truncate_text(text: str, font_set: FontSet, max_width: float, ellipsis: str = "…") -> str:
    """按像素宽度截断纯文本。"""
    if font_set.length(text) <= max_width:
        return text
    truncated = truncate_segments(
        [Segment(text, (255, 255, 255, 255))], font_set, max_width, ellipsis,
    )
    return "".join(segment.text for segment in truncated)




def wrap_segments(
    segments: Sequence[Segment],
    font_set: FontSet,
    max_width: float,
    max_lines: int,
    ellipsis: str = "…",
) -> List[List[Segment]]:
    """按显式换行和像素宽度把富文本折成固定行数。"""
    lines: List[List[Segment]] = [[]]
    used = [0.0]

    def start_line() -> bool:
        if len(lines) >= max_lines:
            return False
        lines.append([])
        used.append(0.0)
        return True

    overflow = False
    for segment in segments:
        for index, chunk in enumerate(segment.text.split("\n")):
            if index and not start_line():
                overflow = True
                break
            if not chunk:
                continue
            buffer: List[str] = []
            for character in chunk:
                width = segment_char_width(segment, character, font_set)
                if used[-1] + width > max_width:
                    if buffer:
                        lines[-1].append(replace(segment, text="".join(buffer)))
                        buffer = []
                    if not start_line():
                        overflow = True
                        break
                buffer.append(character)
                used[-1] += width
            if buffer:
                lines[-1].append(replace(segment, text="".join(buffer)))
            if overflow:
                break
        if overflow:
            break

    if overflow and lines[-1]:
        budget = max_width - font_set.length(ellipsis)
        lines[-1] = truncate_segments(lines[-1], font_set, budget)
        if lines[-1] and lines[-1][-1].text == ellipsis:
            lines[-1].pop()
        tail = lines[-1][-1] if lines[-1] else Segment("", (255, 255, 255, 255))
        lines[-1].append(replace(tail, text=ellipsis, bold=False, obfuscated=False, gradient=None))
    return [line for line in lines if line] or [[]]


__all__ = [
    "Color", "Segment",
    "as_rgba", "with_alpha", "scale_alpha", "resolve_color",
    "relative_luminance", "contrast_ratio",
    "parse_minecraft_formatting",
    "bold_offset", "bold_offset_for", "bold_width", "is_full_width",
    "measure_segments", "measure_text", "segment_char_width",
    "truncate_segments", "truncate_text", "wrap_segments",
]
