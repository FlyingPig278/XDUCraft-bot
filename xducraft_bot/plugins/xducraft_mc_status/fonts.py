"""字体加载。

两套字体各司其职：

- ``Minecraft AE.ttf``：像素风，用于 MOTD、版本号、延迟等“游戏内”信息。
  这套字体自带 6 万多个字形，中文覆盖完整，不会出现豆腐块。
- ``SourceHanSansCN-Medium.otf``：思源黑体，用于 Tag、徽章、说明文字等
  需要清晰易读的界面元素。

字体缺失时回退到 Pillow 默认字体，只是难看，不会让整张图渲染失败。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Union

from nonebot.log import logger
from PIL import ImageFont

from .constants import FONTS_PATH

AnyFont = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]

FONT_MINECRAFT = "Minecraft AE.ttf"
FONT_SOURCE_HAN = "SourceHanSansCN-Medium.otf"


@lru_cache(maxsize=64)
def load_font(font_name: str, size: int) -> AnyFont:
    """按 (文件名, 字号) 加载字体，结果会被缓存。"""
    font_path = os.path.join(FONTS_PATH, font_name)
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, ValueError) as exc:
        logger.warning("[MCStatus] 无法加载字体 {}（{}），回退默认字体。", font_name, exc)
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            # 老版本 Pillow 的 load_default 不接受 size 参数。
            return ImageFont.load_default()


# --- 像素风：游戏内信息 ---
FONT_MC_SMALL = load_font(FONT_MINECRAFT, 17)
FONT_MC_MEDIUM = load_font(FONT_MINECRAFT, 21)
FONT_MC_MOTD = load_font(FONT_MINECRAFT, 29)
FONT_MC_TITLE = load_font(FONT_MINECRAFT, 40)

# --- 思源黑体：界面元素 ---
FONT_ZH_TAG = load_font(FONT_SOURCE_HAN, 27)
FONT_ZH_BADGE = load_font(FONT_SOURCE_HAN, 19)
FONT_ZH_LEGEND = load_font(FONT_SOURCE_HAN, 18)
FONT_ZH_SUMMARY = load_font(FONT_SOURCE_HAN, 22)
FONT_ZH_CREDIT = load_font(FONT_SOURCE_HAN, 19)

__all__ = [
    "load_font",
    "FONT_MC_SMALL", "FONT_MC_MEDIUM", "FONT_MC_MOTD", "FONT_MC_TITLE",
    "FONT_ZH_TAG", "FONT_ZH_BADGE", "FONT_ZH_LEGEND", "FONT_ZH_SUMMARY", "FONT_ZH_CREDIT",
]
