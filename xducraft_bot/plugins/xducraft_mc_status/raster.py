"""绘制原语。

调用方一律用**逻辑单位**（854 宽的画布空间）下指令，这里统一乘 :data:`~.tokens.SCALE`
换算成物理像素。好处有两个：布局代码只需要读参考项目的 CSS 数值就能照搬，
而放大倍率是整数，像素字体和方块材质不会在放大过程中被插值糊掉。

Pillow 本身缺三样这套设计语言必需的能力，都在这里补上：

- **透明度分层。** ``ImageDraw.Draw(image, "RGBA")`` 才会做 alpha 混合，
  默认构造是直接覆盖。整套配色靠黑白透明度叠在材质背景上，没有它就没有设计。
- **跨字体基线对齐。** 混排时每段的 unitsPerEm 不同，必须统一按角色的 ascent
  算出一条基线，逐段用 ``anchor="ls"`` 落笔。
- **粗体 / 斜体 / 渐变。** 正文字体没有粗体字重，斜体和渐变 Pillow 也不做。
  粗体按原版做法重描一遍，斜体走仿射错切，渐变走文字蒙版。
"""

from __future__ import annotations

import os
import random
import string
import zlib
from dataclasses import replace
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from nonebot.log import logger
from PIL import Image, ImageChops, ImageDraw

from . import tokens as t
from .constants import TEXTURES_PATH
from .drawing_utils import (
    Color, Segment, as_rgba, bold_offset_for, bold_width, contrast_ratio,
    measure_segments, relative_luminance, truncate_segments, truncate_text,
)
from .fonts import FontSet

Box = Tuple[float, float, float, float]

#: 斜体错切系数。原版靠逐行右移做斜体，这里用等效的仿射错切，
#: 取值保证一个字高上大约偏移五分之一个字宽——够明显，又不至于压到相邻字。
ITALIC_SHEAR = 0.2

#: ``§k`` 乱码替换用的字符池。原版会随机换成等宽的其他字形，这里同理，
#: 按advance 宽度挑同宽候选，保证乱码不会把整行的排版顶歪。
_OBFUSCATE_POOL = string.ascii_letters + string.digits + "!@#$%&*+=?<>/\\|"
_OBFUSCATE_POOL_CJK = "の㋡区块方界岩石木水火土风雷光暗天地人神鬼龙凤"


# ==============================================================================
# 材质
# ==============================================================================

@lru_cache(maxsize=8)
def load_texture(name: str) -> Optional[Image.Image]:
    """读取一张方块材质并放大到平铺尺寸（最近邻，保持硬像素）。"""
    if not name or name != os.path.basename(name):
        return None
    path = os.path.join(TEXTURES_PATH, name)
    try:
        with Image.open(path) as raw:
            source = raw.convert("RGBA")
            # 有些方块材质是动画图集（竖着叠了很多帧），只取第一帧。
            if source.height > source.width:
                source = source.crop((0, 0, source.width, source.width))
            tile = t.px(t.TEXTURE_TILE)
            return source.resize((tile, tile), Image.Resampling.NEAREST)
    except Exception as exc:
        logger.warning("[MCStatus] 材质 {} 加载失败：{}", name, exc)
        return None


def list_textures() -> List[str]:
    try:
        return sorted(name for name in os.listdir(TEXTURES_PATH) if name.endswith(".png"))
    except OSError:
        return []


# ==============================================================================
# 材质压暗
# ==============================================================================

@lru_cache(maxsize=64)
def texture_scrim(name: str) -> Color:
    """算出把当前材质压到统一目标亮度所需的黑色叠层。

    固定透明度会保留材质原本巨大的亮度差：竹板砖比泥土亮，泥土又比黑色
    混凝土粉末亮。这里在 16×16 样本上二分搜索 alpha，并按 Pillow 实际采用的
    sRGB 混合取整计算输出，因此结果不是伽马公式的近似值。已经比目标暗的材质
    不叠黑；黑色叠层不能把它提亮。
    """
    texture = load_texture(name)
    if texture is None:
        return t.SCRIM
    sample = texture.convert("RGB").resize((16, 16), Image.Resampling.BOX)
    if _mean_luminance(sample) <= t.SCRIM_TARGET_LUMINANCE:
        return (0, 0, 0, 0)

    low, high = 0, int(round(t.SCRIM_MAX_ALPHA * 255))
    while low < high:
        alpha = (low + high) // 2
        if _scrimmed_luminance(sample, alpha) <= t.SCRIM_TARGET_LUMINANCE:
            high = alpha
        else:
            low = alpha + 1
    return (0, 0, 0, low)


def _scrimmed_luminance(sample: Image.Image, alpha: int) -> float:
    """按 Pillow 的 sRGB alpha 混合规则计算压黑后的平均相对亮度。"""
    keep = 255 - alpha
    pixels = sample.getdata()
    total = sum(
        relative_luminance(tuple((channel * keep + 127) // 255 for channel in pixel))
        for pixel in pixels
    )
    return total / (sample.width * sample.height)


def _mean_luminance(texture: Image.Image) -> float:
    """材质的平均相对亮度（线性空间）。"""
    sample = texture.convert("RGB").resize((16, 16), Image.Resampling.BOX)
    pixels = list(sample.getdata())
    return sum(relative_luminance(pixel) for pixel in pixels) / len(pixels)


# ==============================================================================
# 画布
# ==============================================================================

class Canvas:
    """逻辑单位画布。"""

    def __init__(self, width: float, height: float, background: Tuple[int, int, int] = (0, 0, 0)):
        self.width = width
        self.height = height
        # 底图必须是 RGB。``ImageDraw.Draw(image, "RGBA")`` 只有在底图是 RGB 时
        # 才按 alpha 混合；底图是 RGBA 的话它直接覆盖像素，整套“黑白透明度分层”
        # 会全部失效——实测 rgba(0,0,0,.58) 画在灰色上，RGB 底得到 (60,60,60)，
        # RGBA 底得到 (0,0,0,148)，也就是纯黑。
        self.image = Image.new("RGB", (t.px(width), t.px(height)), background)
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    # --- 背景 ---

    def tile_background(self, texture_name: str, scrim: Optional[Color] = None) -> None:
        """平铺方块材质，再压一层黑。没有材质时只留纯黑底。"""
        texture = load_texture(texture_name)
        if texture is None:
            self.draw.rectangle((0, 0, self.image.width, self.image.height), fill=t.SCRIM)
            return

        step = texture.width
        for y in range(0, self.image.height, step):
            for x in range(0, self.image.width, step):
                self.image.paste(texture, (x, y))
        self.draw.rectangle(
            (0, 0, self.image.width, self.image.height),
            fill=scrim if scrim is not None else texture_scrim(texture_name),
        )

    # --- 几何 ---

    def rect(
        self,
        box: Box,
        fill: Optional[Color] = None,
        outline: Optional[Color] = None,
        width: float = t.RULE_WIDTH,
    ) -> None:
        """直角矩形。这套设计里没有圆角，所以也没有 radius 参数。"""
        left, top, right, bottom = (t.px(value) for value in box)
        if right <= left or bottom <= top:
            return
        if fill is not None:
            self.draw.rectangle((left, top, right - 1, bottom - 1), fill=fill)
        if outline is not None:
            self.draw.rectangle(
                (left, top, right - 1, bottom - 1), outline=outline, width=t.px(width),
            )

    def hline(self, y: float, x0: float, x1: float, color: Color, width: float = t.RULE_WIDTH) -> None:
        self.rect((x0, y, x1, y + width), fill=color)

    def vline(self, x: float, y0: float, y1: float, color: Color, width: float = t.RULE_WIDTH) -> None:
        self.rect((x, y0, x + width, y1), fill=color)

    def dotted_vline(self, x: float, y0: float, y1: float, color: Color) -> None:
        """点阵竖线。直线在像素语境里太“矢量”，这里按方块点阵画。"""
        step = t.SPINE_DOT + t.SPINE_GAP
        cursor = y0
        while cursor < y1:
            self.rect((x, cursor, x + t.SPINE_DOT, min(cursor + t.SPINE_DOT, y1)), fill=color)
            cursor += step

    def vertical_gradient(self, box: Box, top: Color, bottom: Color) -> None:
        """竖直渐变。底栏用它做压角：上端全透明，下端半透明黑。

        比一条硬边的深色通栏耐看——硬边会在图片中间横切一刀，而渐变是把
        视线**引**下去。这是这套设计里唯一允许出现的软边。
        """
        left, top_y, right, bottom_y = (t.px(value) for value in box)
        width, height = right - left, bottom_y - top_y
        if width <= 0 or height <= 0:
            return

        column = Image.new("RGBA", (1, height))
        pixels = column.load()
        start, end = as_rgba(top), as_rgba(bottom)
        span = max(1, height - 1)
        for offset in range(height):
            ratio = offset / span
            pixels[0, offset] = tuple(
                int(round(start[channel] + (end[channel] - start[channel]) * ratio))
                for channel in range(4)
            )

        patch = column.resize((width, height), Image.Resampling.NEAREST)
        self.image.paste(patch, (left, top_y), patch)

    def dotted_hline(self, y: float, x0: float, x1: float, color: Color) -> None:
        step = t.SPINE_DOT + t.SPINE_GAP
        cursor = x0
        while cursor < x1:
            self.rect((cursor, y, min(cursor + t.SPINE_DOT, x1), y + t.SPINE_DOT), fill=color)
            cursor += step

    def paste(self, sprite: Image.Image, x: float, y: float) -> None:
        self.image.paste(sprite, (t.px(x), t.px(y)), sprite)

    # --- 文本 ---

    def _baseline(self, y: float, font_set: FontSet, vertical: str) -> float:
        """把逻辑 y 与竖直锚点换算成物理基线坐标。"""
        ascent, descent = font_set.ascent, font_set.descent
        origin = t.px(y)
        if vertical == "m":
            return origin + (ascent - descent) / 2
        if vertical == "a":
            return origin + ascent
        if vertical == "d":
            return origin - descent
        return origin  # "s"：调用方直接给基线

    def text(
        self,
        text: str,
        xy: Tuple[float, float],
        font_set: FontSet,
        fill: Color,
        anchor: str = "lm",
        shadow: bool = True,
    ) -> float:
        """绘制纯文本，返回占用宽度（逻辑单位）。"""
        return self.segments([Segment(text, as_rgba(fill))], xy, font_set, anchor, shadow)

    def segments(
        self,
        segments: Sequence[Segment],
        xy: Tuple[float, float],
        font_set: FontSet,
        anchor: str = "lm",
        shadow: bool = True,
    ) -> float:
        """绘制带样式的分段文本，返回占用宽度（逻辑单位）。"""
        if not segments:
            return 0.0

        horizontal = anchor[0] if anchor and anchor[0] in "lmr" else "l"
        vertical = anchor[1] if len(anchor) > 1 else "m"

        # 字体是按物理字号加载的，所以一切度量天然是物理像素；只在返回值上换回逻辑单位。
        widths = [measure_segments([segment], font_set) for segment in segments]
        total = sum(widths)

        x = t.px(xy[0])
        if horizontal == "r":
            x -= total
        elif horizontal == "m":
            x -= total / 2
        baseline = self._baseline(xy[1], font_set, vertical)
        spans = _gradient_spans(segments, widths, x)

        # Minecraft 投影只留给白色文字。彩色 / 黑色胶片文字不画投影：尤其亮色
        # Tag 自动切成黑字时，原来的黑色投影会糊成一团。
        # 投影仍须整串先画完，再画正文，避免后一段的影子盖住前一段正文。
        if shadow:
            offset = shadow_offset(font_set)
            cursor = x
            for index, segment in enumerate(segments):
                if not has_white_ink(segment):
                    cursor += widths[index]
                    continue
                span = spans[index]
                shifted = None if span is None else (span[0] + offset, span[1])
                dimmed = shadow_of(segment)
                for part, face in font_set.split(segment.text):
                    cursor += self._draw_run(
                        part, face, cursor + offset, baseline + offset,
                        dimmed, font_set, shifted,
                    )

        cursor = x
        for index, segment in enumerate(segments):
            for part, face in font_set.split(segment.text):
                cursor += self._draw_run(
                    part, face, cursor, baseline, segment, font_set, spans[index],
                )
        return total / t.SCALE

    def _draw_run(
        self,
        text: str,
        face,
        x: float,
        baseline: float,
        segment: Segment,
        font_set: FontSet,
        span: Optional[Tuple[float, float]] = None,
    ) -> float:
        """画一段同字体同样式的文本，返回它的物理宽度。"""
        if not text:
            return 0.0

        drawn = _obfuscate(text, face) if segment.obfuscated else text
        width = face.getlength(drawn)
        if segment.bold:
            width += bold_width(drawn, font_set)

        color = as_rgba(segment.color)
        if segment.italic or segment.gradient is not None or color[3] < 255:
            self._draw_run_masked(drawn, face, x, baseline, segment, font_set, width, span)
        else:
            self._stamp(self.draw, drawn, face, x, baseline, color, font_set, segment.bold)

        self._draw_decorations(x, baseline, width, segment, font_set, face)
        return width

    @staticmethod
    def _stamp(
        draw: ImageDraw.ImageDraw, text: str, face, x: float, baseline: float,
        fill, font_set: FontSet, bold: bool,
    ) -> None:
        """落笔。粗体按原版做法重描一遍、右移一个游戏像素。

        非粗体时一次性画完整段，最快。粗体必须逐字走：半角和全角的“一个游戏
        像素”不一样大（见 :func:`.drawing_utils.bold_offset_for`），整段用同一个
        偏移的话，要么英文不够粗、要么中文糊成一团。
        """
        if not bold:
            draw.text((x, baseline), text, font=face, fill=fill, anchor="ls")
            return

        cursor = x
        for character in text:
            offset = bold_offset_for(font_set, character)
            draw.text((cursor, baseline), character, font=face, fill=fill, anchor="ls")
            draw.text((cursor + offset, baseline), character, font=face, fill=fill, anchor="ls")
            cursor += face.getlength(character) + offset

    def _draw_run_masked(
        self, text: str, face, x: float, baseline: float,
        segment: Segment, font_set: FontSet, width: float,
        span: Optional[Tuple[float, float]],
    ) -> None:
        """斜体与渐变都要先把文字画成蒙版，再上色 / 错切。"""
        ascent, descent = face.getmetrics()
        pad = int(ascent * ITALIC_SHEAR) + 4
        size = (int(width) + pad * 2 + 4, ascent + descent + 4)
        origin = (int(x) - pad, int(baseline) - ascent)

        mask = Image.new("L", size, 0)
        self._stamp(
            ImageDraw.Draw(mask), text, face, pad, ascent, 255, font_set, segment.bold,
        )

        if segment.italic:
            # 以基线为支点右倾：基线以上右移，以下左移，和原版观感一致。
            mask = mask.transform(
                size, Image.AFFINE, (1, ITALIC_SHEAR, -ITALIC_SHEAR * ascent, 0, 1, 0),
                resample=Image.Resampling.NEAREST,
            )

        if segment.gradient is not None:
            patch = Image.new("RGBA", size, (0, 0, 0, 0))
            # 渐变要横跨整个 <gradient> 区间。逐段各扫一遍的话，每换一次字体
            # （比如中英交界处）颜色就会跳回起点，看起来像是分了好几段渐变。
            span_start, span_width = span or (x, width)
            sweep = _gradient((max(1, int(span_width)), size[1]), segment.gradient)
            patch.paste(sweep, (int(span_start) - origin[0], 0))
        else:
            patch = Image.new("RGBA", size, as_rgba(segment.color))

        # ``putalpha(mask)`` 会把颜色本身的 alpha 完全覆盖掉，导致 INK_GHOST 等
        # 半透明文本最终仍以 255 不透明度落笔。字形覆盖率与颜色 alpha 必须相乘。
        patch.putalpha(ImageChops.multiply(patch.getchannel("A"), mask))
        self.image.paste(patch, origin, patch)

    def _draw_decorations(
        self, x: float, baseline: float, width: float,
        segment: Segment, font_set: FontSet, face,
    ) -> None:
        if not (segment.underline or segment.strikethrough):
            return
        thickness = max(1, int(font_set.size) // 8)
        color = as_rgba(segment.gradient[0] if segment.gradient else segment.color)
        if segment.underline:
            top = baseline + thickness
            self.draw.rectangle((x, top, x + width - 1, top + thickness - 1), fill=color)
        if segment.strikethrough:
            top = baseline - face.getmetrics()[0] * 0.32
            self.draw.rectangle((x, top, x + width - 1, top + thickness - 1), fill=color)

    # --- 度量（对外一律逻辑单位）---

    @staticmethod
    def measure(text: str, font_set: FontSet) -> float:
        return font_set.length(text) / t.SCALE

    @staticmethod
    def measure_segments(segments: Sequence[Segment], font_set: FontSet) -> float:
        return measure_segments(segments, font_set) / t.SCALE

    @staticmethod
    def fit(segments: Sequence[Segment], font_set: FontSet, max_width: float) -> List[Segment]:
        return truncate_segments(segments, font_set, max_width * t.SCALE)

    @staticmethod
    def fit_text(text: str, font_set: FontSet, max_width: float) -> str:
        return truncate_text(text, font_set, max_width * t.SCALE)


    # --- 输出 ---

    def save(self, path: str) -> str:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.image.save(path, format="PNG", optimize=True)
        return path


# ==============================================================================
# 辅助
# ==============================================================================
def _gradient_spans(
    segments: Sequence[Segment], widths: Sequence[float], origin: float,
) -> List[Optional[Tuple[float, float]]]:
    """把相邻且渐变参数相同的分段归成一组，返回每段所属组的 ``(起点 x, 总宽)``。

    没有这一步，渐变会在每个字体分段的边界重新开始扫描——中英混排的
    ``<gradient>`` 文本会看起来像被切成好几段各自渐变。
    """
    spans: List[Optional[Tuple[float, float]]] = []
    cursor = origin
    group: Optional[Tuple[float, float]] = None

    for index, segment in enumerate(segments):
        if segment.gradient is None:
            spans.append(None)
            cursor += widths[index]
            continue
        if index == 0 or segments[index - 1].gradient != segment.gradient:
            end = index
            total = 0.0
            while end < len(segments) and segments[end].gradient == segment.gradient:
                total += widths[end]
                end += 1
            group = (cursor, total)
        spans.append(group)
        cursor += widths[index]

    return spans


def _gradient(size: Tuple[int, int], stops: Sequence[Color]) -> Image.Image:
    """横向线性渐变，支持任意多个色标。

    两个色标做不出彩虹，而彩虹名字是服务器 MOTD 里很常见的玩法，所以这里在
    参考项目的双色标基础上放开到 N 段：色标把宽度等分，逐段线性插值。
    """
    width, height = size
    palette = [as_rgba(stop) for stop in stops] or [(255, 255, 255, 255)]
    if len(palette) == 1:
        palette = palette * 2

    row = Image.new("RGBA", (max(1, width), 1))
    pixels = row.load()
    span = max(1, width - 1)
    sections = len(palette) - 1

    for index in range(max(1, width)):
        position = index / span * sections
        section = min(int(position), sections - 1)
        ratio = position - section
        start_rgba, end_rgba = palette[section], palette[section + 1]
        pixels[index, 0] = tuple(
            int(round(start_rgba[channel] + (end_rgba[channel] - start_rgba[channel]) * ratio))
            for channel in range(4)
        )
    return row.resize((width, height), Image.Resampling.NEAREST)


@lru_cache(maxsize=2048)
def _same_width_candidates(face, width: float) -> Tuple[str, ...]:
    pool = _OBFUSCATE_POOL + _OBFUSCATE_POOL_CJK
    return tuple(char for char in pool if abs(face.getlength(char) - width) < 0.5) or ("?",)


def _obfuscate(text: str, face) -> str:
    """把每个字换成同宽的随机字形，模拟 ``§k``。

    宽度必须一致，否则乱码段会把整行后面的内容顶歪——静态图里没有动画来
    掩饰这件事，排版错位会非常显眼。

    随机数按原文播种，所以**同一段文字每次得到同一串乱码**。这不是为了可复现，
    而是因为投影和正文要分两趟画：两趟各随机一次的话，影子和字会对不上，
    看起来像是重影。
    """
    generator = random.Random(zlib.crc32(text.encode("utf-8")))
    result: List[str] = []
    for character in text:
        if character.isspace():
            result.append(character)
            continue
        candidates = _same_width_candidates(face, face.getlength(character))
        result.append(generator.choice(candidates))
    return "".join(result)


def shadow_offset(font_set: FontSet) -> int:
    """投影偏移。

    原版把整串文字按 (+1, +1) 个字体像素再画一遍当投影。字体设计在 8×8 的网格上，
    所以一个字体像素 = 字号 / 8。这里对全角字**不**减半——原版的投影是整串平移，
    不随字宽变化，减半反而会让中英混排的影子错位。
    """
    return max(1, int(font_set.size) // 8)


def has_white_ink(segment: Segment) -> bool:
    """只有纯白（透明度不限）的文字使用 Minecraft 投影。"""
    if segment.gradient is not None:
        return all(as_rgba(stop)[:3] == (255, 255, 255) for stop in segment.gradient)
    return as_rgba(segment.color)[:3] == (255, 255, 255)


def shadow_of(segment: Segment) -> Segment:
    """某一段文字的投影颜色。

    原版的算法是 ``(colour & 0xFCFCFC) >> 2``——压到四分之一亮度、保留透明度。
    """
    def dim(color: Color) -> Color:
        red, green, blue, alpha = as_rgba(color)
        return red // 4, green // 4, blue // 4, alpha

    return replace(
        segment,
        color=dim(segment.color),
        gradient=tuple(dim(stop) for stop in segment.gradient) if segment.gradient else None,
    )


def ink_for_background(background: Color) -> Color:
    """在浅底上自动换成黑字，保证 Tag 一类的彩色胶片读得清。

    判据是 WCAG 对比度，取更高的那一边，没有别的调节项。

    旧实现用的是 ``0.299R+0.587G+0.114B >= 186``：那套系数是给**带伽马**的
    sRGB 分量用的经验公式，绿色权重压得太低。亮绿 ``#55FF55`` 因此算出 184.8，
    差 1.2 判成白字，而一样刺眼的黄色 ``#FFFF55`` 拿到黑字。

    中途试过“黑字要明显更好才换”的容差版本，为的是让蓝紫一类中间色保持白字。
    那是错的：``(180, 90, 180)`` 上黑字 5.06、白字 4.15，容差会选中白字——
    而白字连 WCAG AA 的 4.5 都不到。**可读性不是可以拿来换观感的东西。**
    """
    if contrast_ratio(t.INK_DARK, background) > contrast_ratio(t.INK, background):
        return t.INK_DARK
    return t.INK


def ping_tier(ping: Optional[int], online: bool) -> str:
    """延迟档位。离线单独一档，信号条会一格都不亮。"""
    if not online or ping is None:
        return "dead"
    good, fair, poor = t.PING_TIER_THRESHOLDS
    if ping < good:
        return "excellent"
    if ping < fair:
        return "good"
    if ping < poor:
        return "fair"
    return "poor"


TIER_COLORS = {
    "excellent": t.STATE_EXCELLENT,
    "good": t.STATE_GOOD,
    "fair": t.STATE_FAIR,
    "poor": t.STATE_POOR,
    "dead": t.STATE_DEAD,
}

TIER_BARS = {"excellent": 5, "good": 4, "fair": 3, "poor": 2, "dead": 0}


__all__ = [
    "Canvas", "Box", "load_texture", "list_textures",
    "ink_for_background", "ping_tier", "TIER_COLORS", "TIER_BARS",
]
