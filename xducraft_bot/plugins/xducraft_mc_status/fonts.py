"""字体角色与逐字回退。

## 为什么需要“逐字回退”

参考项目跑在浏览器里，靠 CSS ``unicode-range`` 白拿字体回退。Pillow **没有回退**：
它拿一个字体文件从头画到尾，缺字就画 ``.notdef``（豆腐块）。实测过：

    minecraft-ten.ttf        551 字形   '服' 与 '器' 的位图完全相同 -> 都是豆腐
    minecraft-five-bold.otf  119 字形   同上
    Monocraft.otf            293 字形   同上
    minecraft.ttf            206 字形   干脆一个像素都不画
    Minecraft AE.ttf       63446 字形   中英全覆盖

所以标题里的“服务器状态”如果直接交给 Minecraft Ten，出来的就是六个方框。
:class:`FontSet` 把一串字按“哪个字体真的有这个字形”切成若干段，逐段绘制。

判断“有没有这个字形”不引入 fontTools：直接把 U+FFFF（Unicode 永久保留的
非字符，任何字体都不会映射）画一遍取得该字体的豆腐位图指纹，再拿目标字符的
位图和它比。缺字要么画出一模一样的豆腐，要么一片空白，两种都能识别。

## 为什么字号不能随便填

这些像素字体是“描摹像素网格的矢量字体”，字号不是网格步长的整数倍时，
FreeType 会把本该非黑即白的边缘插值成灰。实测（统计栅格里的灰阶数量，
2 = 纯像素，30+ = 糊）：

    Minecraft AE   16px->2   24px->2   32px->2   40px->2      ← 8 的倍数
                   17px->32  21px->33  29px->33               ← 旧实现用的就是这些
    Vonwaon 12px   12px->2   24px->2   36px->2   48px->2      ← 12 的倍数
                   16px->12  18px->5   26px->42
    Monocraft      各字号都是 30+，它本来就是带抗锯齿的编程字体，不受此限

因此：**Minecraft AE 的物理字号必须是 8 的倍数，Vonwaon 必须是 12 的倍数。**
:data:`_GRID` 在导入时校验，写错字号会直接告警，不会悄悄糊掉。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from nonebot.log import logger
from PIL import Image, ImageDraw, ImageFont

from .constants import FONTS_PATH
from .tokens import (
    TYPE_ADDRESS, TYPE_CHIP, TYPE_DATA, TYPE_EYEBROW, TYPE_LABEL,
    TYPE_MICRO, TYPE_MOTD, TYPE_SUBTITLE, TYPE_TITLE, px,
)

# ==============================================================================
# 1. 字体文件
# ==============================================================================

#: 正文兼中日韩：6.3 万字形，一个文件全包，是这套字体里唯一不需要回退的。
FACE_BODY = "Minecraft AE.ttf"
#: 标题：带立体描边的展示体，仅 ASCII。
FACE_DISPLAY = "minecraft-ten.ttf"
#: 强调标签：粗体小字，仅 ASCII。
FACE_LABEL = "minecraft-five-bold.otf"
#: 数字：等宽，延迟/人数/版本号用它对齐。仅 ASCII。
FACE_DATA = "Monocraft.otf"
#: 展示体与标签体的中日韩搭档：12px 点阵，唯一能在整数倍字号下做到纯像素的中文字体。
FACE_CJK_PIXEL = "VONWAONBITMAP-12PX.TTF"

# 思源黑体（``SourceHanSansCN-Medium.otf``）还留在 resources/fonts 里，但状态图
# 已经不用它了——一款平滑的无衬线体挨着像素字体，正是旧版最不像 Minecraft 的
# 地方。**不要删这个文件**：``xducraft_wordcloud`` 会跨插件目录直接引用它来渲染
# 中文词云（见该插件的 ``_get_font_path``），删掉词云会静默退化成豆腐块。

#: 物理字号必须落在各自的像素网格上，否则 FreeType 会插值出灰边。
_GRID: Dict[str, int] = {
    FACE_BODY: 8,
    FACE_CJK_PIXEL: 12,
}

#: 用来取“豆腐指纹”的码位。U+FFFF 是 Unicode 永久非字符，不可能被映射。
_NOTDEF_PROBE = "\uffff"


@lru_cache(maxsize=128)
def load_face(file_name: str, size: int) -> Optional[ImageFont.FreeTypeFont]:
    """按 (文件名, 物理字号) 加载字体；失败返回 ``None`` 交给下一级回退。"""
    step = _GRID.get(file_name)
    if step and size % step:
        logger.warning(
            "[MCStatus] 字号 {}px 不是 {} 的像素网格（{} 的倍数），会渲染出灰边。",
            size, file_name, step,
        )

    path = os.path.join(FONTS_PATH, file_name)
    try:
        return ImageFont.truetype(path, size)
    except (OSError, ValueError) as exc:
        logger.warning("[MCStatus] 无法加载字体 {}（{}）。", file_name, exc)
        return None


@lru_cache(maxsize=128)
def _signature(font: ImageFont.FreeTypeFont, character: str) -> bytes:
    """某个字符在该字体下的位图指纹。"""
    size = max(8, int(getattr(font, "size", 16) or 16))
    canvas = Image.new("L", (size * 3, size * 3), 0)
    ImageDraw.Draw(canvas).text((size // 2, size // 2), character, font=font, fill=255)
    return canvas.tobytes()


@lru_cache(maxsize=128)
def _blank_signature(font: ImageFont.FreeTypeFont) -> bytes:
    size = max(8, int(getattr(font, "size", 16) or 16))
    return Image.new("L", (size * 3, size * 3), 0).tobytes()


@lru_cache(maxsize=4096)
def covers(font: ImageFont.FreeTypeFont, character: str) -> bool:
    """该字体是否真的有这个字符的字形。

    空白字符一律算“有”——它本来就该什么都不画，不能因为位图为空被判成缺字。
    """
    if character.isspace():
        return True
    signature = _signature(font, character)
    if signature == _blank_signature(font):
        return False
    return signature != _signature(font, _NOTDEF_PROBE)


# ==============================================================================
# 2. Latin-1 补丁
# ==============================================================================

#: Minecraft AE 把 U+00A0–U+00FF **整块**当成原版的“重音字符页”用了：``·`` 画出
#: 来是 ``Ù``、``»`` 是 ``Þ``、``×`` 是 ``Ü``、``©`` 是 ``Ì``……只有真正的重音字母
#: （``é`` ``ü``）是对的。:func:`covers` 抓不到这种错——字形存在，只是画错了字。
#:
#: 所以只能显式改写。替换目标全部实测过：ASCII 正常，``‧``（U+2027）正常，
#: 高位 Unicode 标点不受这套错误映射影响。
_LATIN1_REMAP = {
    "\u00b7": "\u2027",  # · -> ‧
    "\u00bb": ">", "\u00ab": "<",
    "\u00d7": "x", "\u00f7": "/",
    "\u00a9": "(c)", "\u00ae": "(r)",
    "\u00b0": "deg", "\u00b1": "+/-",
    "\u00bc": "1/4", "\u00bd": "1/2", "\u00be": "3/4",
    "\u00a1": "!", "\u00bf": "?",
    "\u00a0": " ",
}


def remap(text: str) -> str:
    """把画错的 Latin-1 标点换成等价写法。度量与绘制都要经过它，两边才对得上。"""
    if not text:
        return text
    return "".join(_LATIN1_REMAP.get(character, character) for character in text)


# ==============================================================================
# 3. 字体角色
# ==============================================================================

class FontSet:
    """一个排版角色：一串按优先级排列的字体，逐字挑第一个画得出来的。"""

    __slots__ = ("name", "size", "faces")

    def __init__(self, name: str, size: int, files: Sequence[str]):
        self.name = name
        self.size = size
        faces = [face for face in (load_face(file, size) for file in files) if face is not None]
        if not faces:
            fallback = ImageFont.load_default()
            logger.error("[MCStatus] 角色 {} 没有任何可用字体，回退到默认字体。", name)
            faces = [fallback]
        self.faces: Tuple[ImageFont.FreeTypeFont, ...] = tuple(faces)

    @property
    def primary(self) -> ImageFont.FreeTypeFont:
        return self.faces[0]

    def face_for(self, character: str) -> ImageFont.FreeTypeFont:
        for face in self.faces:
            if covers(face, character):
                return face
        # 谁都画不出来时交给首选字体，让豆腐块暴露问题，而不是静默吞字。
        return self.faces[0]

    def split(self, text: str) -> List[Tuple[str, ImageFont.FreeTypeFont]]:
        """把文本切成 ``(连续同字体的片段, 字体)``，顺带修掉 Latin-1 错映射。"""
        text = remap(text)
        runs: List[Tuple[str, ImageFont.FreeTypeFont]] = []
        if not text:
            return runs

        buffer: List[str] = []
        current = self.face_for(text[0])
        for character in text:
            face = self.face_for(character)
            if face is not current and buffer:
                runs.append(("".join(buffer), current))
                buffer = []
            current = face
            buffer.append(character)
        if buffer:
            runs.append(("".join(buffer), current))
        return runs

    def length(self, text: str) -> float:
        """文本宽度。必须按分段量，跨字体时单一 ``getlength`` 会算错。"""
        return sum(face.getlength(part) for part, face in self.split(text))

    def char_length(self, character: str) -> float:
        return self.length(character)

    @property
    def ascent(self) -> float:
        """角色基线高度。跨 unitsPerEm 混排时，所有分段都对齐到这条基线。"""
        return max(face.getmetrics()[0] for face in self.faces)

    @property
    def descent(self) -> float:
        return max(face.getmetrics()[1] for face in self.faces)

    @property
    def height(self) -> float:
        return self.ascent + self.descent


# --- 角色实例（字号是物理像素，由逻辑字号乘 SCALE 得到）---

#: 顶栏品牌行。
EYEBROW = FontSet("eyebrow", px(TYPE_EYEBROW), (FACE_LABEL, FACE_CJK_PIXEL, FACE_BODY))
#: 图片主标题。
TITLE = FontSet("title", px(TYPE_TITLE), (FACE_DISPLAY, FACE_CJK_PIXEL, FACE_BODY))
#: 顶栏概览行。
SUBTITLE = FontSet("subtitle", px(TYPE_SUBTITLE), (FACE_BODY,))
#: 卡片两行 MOTD。
MOTD = FontSet("motd", px(TYPE_MOTD), (FACE_BODY,))
#: 顶栏右侧的概览胶片与卡片 Tag。
CHIP = FontSet("chip", px(TYPE_CHIP), (FACE_BODY,))
#: 地址行。
ADDRESS = FontSet("address", px(TYPE_ADDRESS), (FACE_BODY,))
#: 玩家列表与署名。
MICRO = FontSet("micro", px(TYPE_MICRO), (FACE_BODY,))
#: 延迟与人数计数器。等宽体只有 ASCII，混进中文时自动回退正文体。
DATA = FontSet("data", px(TYPE_DATA), (FACE_DATA, FACE_BODY))
#: 版本号：与 DATA 完全同字号，但固定使用普通 Minecraft 字体。
VERSION = FontSet("version", px(TYPE_DATA), (FACE_BODY,))
#: OFFLINE 等状态词。
LABEL = FontSet("label", px(TYPE_LABEL), (FACE_LABEL, FACE_CJK_PIXEL, FACE_BODY))

__all__ = [
    "FACE_BODY", "FACE_DISPLAY", "FACE_LABEL", "FACE_DATA", "FACE_CJK_PIXEL",
    "load_face", "covers", "FontSet",
    "EYEBROW", "TITLE", "SUBTITLE", "CHIP", "MOTD", "ADDRESS", "MICRO",
    "DATA", "VERSION", "LABEL",
]
