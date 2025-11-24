# 1. 标准库导入
import re
from math import ceil
from typing import List, Dict, Any

# 2. 第三方库导入
from PIL import Image, ImageDraw, ImageFile

# 3. 本地应用/项目特定导入
from .constants import *
from .data_manager import get_footer
from .decode_image import decode_image
from .drawing_utils import draw_colored_title_html, calculate_clean_length
from .fonts import FONT_MC_SMALL, FONT_MC_MEDIUM, FONT_MC_MOTD, FONT_ZH_TAG, FONT_MC_TITLE, FONT_ZH_CREDIT
from .status_fetcher import preprocess_server_data, prepare_data_for_display

ImageFile.LOAD_TRUNCATED_IMAGES = True

if not os.path.exists(SAVE_IMG_DIR):
    os.makedirs(SAVE_IMG_DIR)


def _calculate_recursive_height(server_nodes: List[Dict[str, Any]]) -> int:
    """递归地计算渲染服务器节点列表所需的总高度。"""
    height = 0
    for server in server_nodes:
        height += SERVER_ROW_HEIGHT
        if server.get('online') and server.get('players', {}).get('online') != 0 and server.get('players', {}).get('sample'):
            height += PLAYER_LIST_OFFSET
        if 'children' in server and server['children']:
            height += _calculate_recursive_height(server['children'])
    return height


def calculate_image_height(display_data: List[Dict[str, Any]], footer_text: str) -> int:
    """根据服务器树和页脚计算最终图片的高度。"""
    total_height = LAYOUT_TITLE_AREA_HEIGHT
    total_height += _calculate_recursive_height(display_data)
    if footer_text:
        total_height += LAYOUT_FOOTER_AREA_HEIGHT
    total_height += LAYOUT_CREDIT_AREA_HEIGHT
    return total_height


async def _draw_server_row(img: Image.Image, draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int,
                           horizontal_offset: int):
    """绘制单个服务器条目（图标, MOTD, IP, 状态, 玩家列表）。"""
    info = server_data
    tag = info.get('tag')
    tag_color_hex = info.get('tag_color')

    await _draw_icon(img, server_data, current_y, horizontal_offset)
    tag_total_width = _draw_tag_with_background(draw, tag, tag_color_hex, current_y, horizontal_offset)
    _draw_motd(draw, server_data, current_y, horizontal_offset, tag_total_width)
    _draw_hostname(draw, server_data, current_y, horizontal_offset)
    _draw_status_info(draw, server_data, current_y)


async def _recursive_draw_servers(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    nodes: List[Dict[str, Any]],
    y_cursor: int,
    level: int = 0,
    parent_had_players: bool = False
) -> int:
    """
    递归地绘制服务器树。
    返回绘制完成后的新y坐标。
    """
    for i, server_data in enumerate(nodes):
        is_first_child = (i == 0)
        is_last_child = (i == len(nodes) - 1)
        horizontal_offset = level * CHILD_INDENT_PX

        if level > 0:
            _draw_connector_line(draw, y_cursor, is_first_child, is_last_child, level, parent_had_players)

        await _draw_server_row(img, draw, server_data, y_cursor, horizontal_offset)

        current_server_has_players = bool(
            server_data.get('online') and 
            server_data.get('players', {}).get('online') != 0 and 
            server_data.get('players', {}).get('sample')
        )

        y_cursor += SERVER_ROW_HEIGHT
        if current_server_has_players:
            y_cursor += PLAYER_LIST_OFFSET

        if 'children' in server_data and server_data['children']:
            y_cursor = await _recursive_draw_servers(
                img, draw, server_data['children'], y_cursor, level + 1, parent_had_players=current_server_has_players
            )

    return y_cursor


async def render_status_image(server_data_list: List[Dict[str, Any]], group_id: int, show_all_servers: bool) -> str:
    """从树形结构渲染Minecraft服务器状态图片。"""
    clean_data = preprocess_server_data(server_data_list)
    display_data = prepare_data_for_display(clean_data, show_all_servers)
    footer_text = get_footer(group_id)

    image_height = calculate_image_height(display_data, footer_text)

    img = Image.new('RGBA', (IMAGE_WIDTH, image_height), color=CANVAS_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    _draw_header_and_background(draw, image_height, bool(footer_text))

    list_start_y = LAYOUT_TITLE_AREA_HEIGHT + OFFSET_SERVER_LIST_START_Y
    await _recursive_draw_servers(img, draw, display_data, list_start_y)

    _draw_footer_and_credit(draw, image_height, footer_text)

    img_path = os.path.join(SAVE_IMG_DIR, f"mc_status_{group_id}.png")
    img.save(img_path)
    return img_path


# --- 绘图辅助函数 ---

def _draw_header_and_background(draw: ImageDraw.ImageDraw, image_height: int, footer_exists: bool):
    """绘制背景矩形和主标题。"""
    content_end_y = image_height - LAYOUT_CREDIT_AREA_HEIGHT
    if footer_exists:
        content_end_y -= LAYOUT_FOOTER_AREA_HEIGHT

    draw.rectangle(xy=(0, LAYOUT_TITLE_AREA_HEIGHT, IMAGE_WIDTH, content_end_y), fill=MAIN_CONTENT_BACKGROUND_COLOR)
    draw.text(xy=(IMAGE_WIDTH / 2, LAYOUT_TITLE_AREA_HEIGHT / 2), text="Minecraft服务器状态",
              fill=PRIMARY_TEXT_COLOR, font=FONT_MC_TITLE, anchor='mm')


def _draw_footer_and_credit(draw: ImageDraw.ImageDraw, image_height: int, footer_text: str):
    """在底部绘制页脚和鸣谢文本。"""
    if footer_text:
        footer_y = image_height - LAYOUT_CREDIT_AREA_HEIGHT - (LAYOUT_FOOTER_AREA_HEIGHT / 2)
        draw.text((LAYOUT_BASE_PADDING, footer_y), text=footer_text, anchor="lm",
                  fill=PRIMARY_TEXT_COLOR, font=FONT_MC_MEDIUM)

    credit_y = image_height - (LAYOUT_CREDIT_AREA_HEIGHT / 2)
    draw.text((IMAGE_WIDTH / 2, credit_y), "Powered by FlyingPig278, LITTLE-UNIkeEN",
              fill=CREDIT_TEXT_COLOR, font=FONT_ZH_CREDIT, anchor="mm")


async def _draw_icon(img: Image.Image, server_data: Dict[str, Any], current_y: int, horizontal_offset: int):
    """绘制服务器的favicon。"""
    icon_url = server_data.get("favicon")
    if icon_url:
        icon_bytes = await decode_image(icon_url)
        if icon_bytes:
            try:
                with Image.open(icon_bytes) as img_avatar:
                    img_avatar = img_avatar.resize((LAYOUT_SERVER_ICON_SIZE, LAYOUT_SERVER_ICON_SIZE)).convert("RGBA")
                    img.paste(img_avatar, (horizontal_offset + LAYOUT_BASE_PADDING, current_y), img_avatar)
            except Exception as e:
                print(f"粘贴服务器图标失败 {server_data.get('ip')}: {e}")


def _draw_tag_with_background(draw: ImageDraw.ImageDraw, tag: str, tag_color_hex: str, current_y: int,
                              horizontal_offset: int) -> int:
    """绘制带彩色背景的服务器标签，并返回其宽度。"""
    if not tag:
        return 0

    fill_color = f"#{tag_color_hex}" if tag_color_hex else TAG_DEFAULT_BACKGROUND
    tag_text = tag

    bbox = draw.textbbox((0, 0), tag_text, font=FONT_ZH_TAG)
    tag_text_height = int(ceil(bbox[3] - bbox[1]))
    tag_text_width = int(ceil(bbox[2] - bbox[0]))

    rect_width = tag_text_width + 2 * TAG_PADDING_X
    rect_height = tag_text_height + 2 * TAG_PADDING_Y
    tag_start_x = horizontal_offset + LAYOUT_BASE_PADDING + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING

    x0, y0 = tag_start_x, current_y
    x1, y1 = x0 + rect_width, y0 + rect_height

    draw.rounded_rectangle(xy=(x0, y0, x1, y1), fill=fill_color, radius=3)
    draw.text(xy=(x0 + rect_width / 2, y0 + rect_height / 2), text=tag_text,
              fill=TAG_TEXT_COLOR, font=FONT_ZH_TAG, anchor='mm')

    return rect_width + ICON_TEXT_SPACING


def _draw_motd(draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int, horizontal_offset: int,
               tag_total_width: int = 0):
    """解析并绘制服务器MOTD。"""
    motd_start_x = horizontal_offset + LAYOUT_BASE_PADDING + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING + tag_total_width

    # 首先处理离线服务器
    if not server_data.get('online'):
        comment = server_data.get('comment')
        offline_text = comment if comment else "服务器离线"
        draw.text((motd_start_x, current_y), offline_text, fill=SECONDARY_TEXT_COLOR, font=FONT_MC_MOTD)
        return

    # --- 在线服务器逻辑 ---
    motd_text = "未获取到MOTD"
    description_data = server_data.get("description")

    if isinstance(description_data, dict):
        title = description_data.get('html') or description_data.get('text', 'Unknown Server Name')
        title = title.replace('服务器已离线...', '')
        check_title = title.replace('<br>', ' | ')
        is_html_mode = 'html' in description_data

        # 简单的截断逻辑 (如果需要可以改进)
        max_len_px = IMAGE_WIDTH - motd_start_x - 100  # 为ping/players保留空间
        if title == 'A Minecraft Server' and server_data.get('comment'):
            final_title = server_data.get('comment')
        elif calculate_clean_length(check_title, FONT_MC_MOTD, is_html=is_html_mode) > max_len_px:
            final_title = title.split('<br>', 1)[0]
        else:
            final_title = check_title

        if is_html_mode:
            draw_colored_title_html(draw, final_title, (motd_start_x, current_y), font=FONT_MC_MOTD)
        else:
            final_title = re.sub(r'§[klmno]', '', final_title)
            try:
                from .drawing_utils import draw_colored_title
                draw_colored_title(draw, final_title, (motd_start_x, current_y), font=FONT_MC_MOTD)
            except ImportError:
                draw.text((motd_start_x, current_y), final_title, fill=PRIMARY_TEXT_COLOR, font=FONT_MC_MOTD)

    else:
        draw.text((motd_start_x, current_y), motd_text, fill=SECONDARY_TEXT_COLOR, font=FONT_MC_MOTD)


def _draw_hostname(draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int, horizontal_offset: int):
    """绘制服务器的主机名/IP。"""
    hide_ip = server_data.get('hide_ip', False)
    display_name = server_data.get('display_name', '')
    
    hostname_text = ""
    if hide_ip:
        hostname_text = display_name if display_name else "[IP已隐藏]"
    else:
        # 保持原有的IP和端口格式化逻辑
        hostname_text = server_data.get('ip', '未知服务器')

    draw.text((horizontal_offset + LAYOUT_BASE_PADDING + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING, current_y + OFFSET_IP_Y),
              hostname_text, fill=SECONDARY_TEXT_COLOR, font=FONT_MC_MEDIUM)


def _draw_status_info(draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int):
    """绘制右对齐的状态信息 (ping, 玩家数, 版本, 玩家列表)。"""
    if server_data.get('online'):
        ping = int(server_data.get('ping', 0))
        ping_color = PING_COLOR_RED if ping >= 100 else PING_COLOR_GREEN
        ping_text = f"{ping}ms"
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y), ping_text, fill=ping_color, anchor='ra', font=FONT_MC_MEDIUM)

        players_text = f"{server_data.get('players', {}).get('online', 'N/A')}/{server_data.get('players', {}).get('max', 'N/A')}"
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_PLAYER_COUNT_Y), players_text,
                  fill=SECONDARY_TEXT_COLOR, anchor='ra', font=FONT_MC_MEDIUM)

        version_info = server_data.get('version')
        if isinstance(version_info, dict):
            version_text = version_info.get('name', 'N/A')
        elif isinstance(version_info, str):
            version_text = version_info
        else:
            version_text = 'N/A'
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_VERSION_Y), version_text,
                  fill=SECONDARY_TEXT_COLOR, anchor='ra', font=FONT_MC_MEDIUM)

        player_sample = server_data.get('players', {}).get('sample')
        if server_data.get('players', {}).get('online') != 0 and player_sample:
            player_names = ", ".join([p['name'] for p in player_sample])
            if draw.textlength(player_names, font=FONT_MC_SMALL) > IMAGE_WIDTH / 2:
                player_names = player_names[:40] + "..."
            player_text = f"{player_names} 正在游玩"

            draw.text(xy=(IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_PLAYER_LIST_Y),
                      text='●', fill=PING_COLOR_GREEN, anchor='ra', font=FONT_MC_SMALL)
            draw.text(xy=(IMAGE_WIDTH - LAYOUT_BASE_PADDING - draw.textlength('●', font=FONT_MC_SMALL) - PLAYER_LIST_DOT_SPACING,
                          current_y + OFFSET_PLAYER_LIST_Y),
                      text=player_text, fill=SECONDARY_TEXT_COLOR, anchor='ra', font=FONT_MC_SMALL)
    else:
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y), "offline",
                  fill=PING_COLOR_RED, anchor='ra', font=FONT_MC_MEDIUM)
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_PLAYER_COUNT_Y), "服务器离线",
                  fill=SECONDARY_TEXT_COLOR, anchor='ra', font=FONT_MC_MEDIUM)


def _draw_connector_line(draw: ImageDraw.ImageDraw, current_y: int, is_first_child: bool, is_last_child: bool, level: int, parent_had_players: bool):
    """为子服务器绘制L形的连接线。"""
    main_trunk_x = LAYOUT_BASE_PADDING + (level - 1) * CHILD_INDENT_PX + (LAYOUT_SERVER_ICON_SIZE / 2)
    branch_x_end = LAYOUT_BASE_PADDING + level * CHILD_INDENT_PX
    line_y = current_y + (LAYOUT_SERVER_ICON_SIZE / 2)

    # 绘制水平分支
    draw.line(xy=(main_trunk_x, line_y, branch_x_end, line_y), fill=CONNECTOR_LINE_COLOR, width=CONNECTOR_LINE_THICKNESS)

    # 计算垂直线的起始Y坐标
    if is_first_child:
        start_y = current_y - SERVER_ROW_HEIGHT
        if parent_had_players:
            start_y -= PLAYER_LIST_OFFSET
        start_y += LAYOUT_SERVER_ICON_SIZE # 从父图标的底部开始
    else:
        start_y = current_y # 从当前行的顶部开始

    # 计算垂直线的结束Y坐标
    end_y = line_y if is_last_child else (current_y + SERVER_ROW_HEIGHT)

    # 绘制垂直主干
    if end_y > start_y:
        draw.line(xy=(main_trunk_x, start_y, main_trunk_x, end_y), fill=CONNECTOR_LINE_COLOR, width=CONNECTOR_LINE_THICKNESS)