import os
from typing import Union

from PIL import ImageFont

from xducraft_bot.plugins.xducraft_mc_status.constants import FONTS_PATH

# --- 字体加载 ---
def load_font(font_name: str, size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    font_path = os.path.join(FONTS_PATH, font_name)
    try:
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"文件不存在：{font_path}")

        # 检查文件是否可读
        if not os.access(font_path, os.R_OK):
            raise IOError(f"文件不可读：{font_path}")

        # 尝试加载字体
        return ImageFont.truetype(font_path, size)
    except (FileNotFoundError, IOError, OSError) as e:
        print(f"无法加载字体{font_name}，尝试使用默认字体。错误：{e}")
        return ImageFont.load_default(size=size)


FONT_MC_SMALL = load_font('Minecraft AE.ttf', 16)
FONT_MC_MEDIUM = load_font('Minecraft AE.ttf', 20)
FONT_MC_MOTD = load_font('Minecraft AE.ttf', 30)
FONT_MC_TITLE = load_font('Minecraft AE.ttf', 39)
FONT_ZH_CREDIT = load_font('SourceHanSansCN-Medium.otf', 20)
FONT_ZH_TAG = load_font('SourceHanSansCN-Medium.otf', 30)
