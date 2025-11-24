import re
from typing import Tuple

from PIL import ImageDraw, ImageFont, ImageColor

from xducraft_bot.plugins.xducraft_mc_status.constants import MINECRAFT_COLOR_CODES, HTML_COLOR_CODES


def draw_colored_title(draw: ImageDraw.ImageDraw,
                       text: str,
                       position: Tuple[int, float],
                       font: ImageFont.FreeTypeFont,
                       default_color: Tuple[int, int, int, int] = (255, 255, 255, 255)):
    x, y = position
    current_color = default_color
    buffer_text = ''
    i = 0
    while i < len(text):
        if text[i] == '§':
            if buffer_text:
                draw.text((x, y), buffer_text, fill=current_color, font=font,anchor="lm")
                size = draw.textlength(buffer_text, font=font)
                x += size
                buffer_text = ''
            if i + 1 < len(text) and text[i + 1].lower() in MINECRAFT_COLOR_CODES:
                current_color = MINECRAFT_COLOR_CODES.get(text[i + 1].lower(), default_color)
            i += 2
        else:
            buffer_text += text[i]
            i += 1
    if buffer_text:
        draw.text((x, y), buffer_text, fill=current_color, font=font,anchor="lm")


def draw_colored_title_html(draw: ImageDraw.ImageDraw,
                            text: str,
                            position: Tuple[int, float],
                            font: ImageFont.FreeTypeFont,
                            default_color: Tuple[int, int, int, int] = (255, 255, 255, 255)):
    x, y = position
    parts = re.split(r'(<font color=\".*?\">)', text)
    current_color = default_color
    for part in parts:
        if part.startswith('<font color=\"'):
            html_color_name_match = re.search(r'\"(.+?)\"', part)
            if html_color_name_match:
                html_color_name = html_color_name_match.group(1)
                if html_color_name:
                    current_color = HTML_COLOR_CODES.get(html_color_name, default_color)
                    if current_color == default_color and html_color_name not in HTML_COLOR_CODES:
                        try:
                            current_color = ImageColor.getrgb(html_color_name)
                        except ValueError:
                            current_color = default_color
                else:
                    current_color = default_color
            else:
                current_color = default_color
        else:
            clean_text = re.sub(r'<.*?>', '', part)
            if clean_text:
                draw_colored_title(draw, clean_text, (x, y), font, current_color)
                size = draw.textlength(clean_text, font=font)
                x += size


def calculate_clean_length(text: str, font: ImageFont.FreeTypeFont, is_html: bool) -> int:
    """
    计算包含颜色/格式码的字符串，在画布上渲染的实际像素长度。

    Args:
        text (str): 包含颜色码（§或<font>）的字符串。
        font (ImageFont.FreeTypeFont): 绘制使用的字体。
        is_html (bool): True 表示使用 HTML/font 标签解析，False 表示使用 Minecraft § 码解析。
    """
    total_length = 0

    if is_html:
        # --- HTML 长度计算逻辑 ---
        # 模拟 draw_colored_title_html：先剥离 HTML 标签
        parts = re.split(r'(<font color=\".*?\">)', text)
        for part in parts:
            if part.startswith('<font color=\"'):
                continue  # 跳过颜色标签
            clean_text = re.sub(r'<.*?>', '', part)
            if clean_text:
                # HTML 模式下，clean_text 仍然可能包含 § 码
                # 所以我们递归调用 Minecraft 长度计算来处理这部分
                total_length += _calculate_minecraft_length(clean_text, font)
    else:
        # --- Minecraft § 长度计算逻辑 (无 HTML) ---
        # 这一逻辑与 draw_colored_title 对应
        total_length = _calculate_minecraft_length(text, font)

    return int(total_length)


def _calculate_minecraft_length(text_with_mc_codes: str, font: ImageFont.FreeTypeFont) -> int:
    """ 内部函数：计算只包含 Minecraft § 码的字符串长度。 """
    length = 0
    buffer_text = ''
    i = 0
    while i < len(text_with_mc_codes):
        if text_with_mc_codes[i] == '§':
            if buffer_text:
                length += font.getlength(buffer_text)
                buffer_text = ''
            i += 2  # 跳过 § 和后面的颜色字符/格式码
        else:
            buffer_text += text_with_mc_codes[i]
            i += 1

    if buffer_text:
        length += font.getlength(buffer_text)

    return int(length)
