# 1. 标准库导入
import os
import re
from typing import List, Dict, Any

# 2. 第三方库导入
from PIL import Image, ImageDraw, ImageFile

# 3. 本地应用/项目特定导入 (按字母顺序排列)
from .constants import (
    SAVE_IMG_DIR, CANVAS_BACKGROUND_COLOR, SECONDARY_TEXT_COLOR, PING_COLOR_RED, PING_COLOR_GREEN,
    LAYOUT_TITLE_AREA_HEIGHT, LAYOUT_BASE_PADDING, LAYOUT_SERVER_ICON_SIZE, IMAGE_WIDTH, ICON_TEXT_SPACING,
    CHILD_INDENT_PX, SERVER_ROW_HEIGHT, PLAYER_LIST_OFFSET, OFFSET_IP_Y, OFFSET_PLAYER_COUNT_Y,
    OFFSET_VERSION_Y, OFFSET_SERVER_LIST_START_Y, OFFSET_PLAYER_LIST_Y, PLAYER_LIST_DOT_SPACING, TAG_PADDING_X,
    TAG_PADDING_Y, TAG_TEXT_COLOR, TAG_DEFAULT_BACKGROUND, CONNECTOR_LINE_COLOR,
    CONNECTOR_LINE_THICKNESS
)
from .data_manager import get_footer
from .decode_image import decode_image
from .drawing_utils import draw_colored_title, draw_colored_title_html, calculate_clean_length
from .fonts import FONT_MC_SMALL, FONT_MC_MEDIUM, FONT_MC_MOTD, FONT_ZH_TAG
from .status_fetcher import preprocess_server_data, prepare_data_for_display, get_active_server_count

# 允许加载被截断的图片，以防止因网络问题导致的加载失败
ImageFile.LOAD_TRUNCATED_IMAGES = True

# 定义字体和图片保存路径
if not os.path.exists(SAVE_IMG_DIR):
    os.makedirs(SAVE_IMG_DIR)


async def render_status_image(server_data_list: List[Dict[str, Any]], group_id: int, show_all_servers: bool) -> str:
    """
    渲染MC服务器状态图片
    """
    # 1. 数据准备
    clean_data = preprocess_server_data(server_data_list) # 处理匿名玩家
    display_data = prepare_data_for_display(clean_data, show_all_servers) # 排序，并过滤离线服务器
    footer_text = get_footer(group_id) # 获取footer

    # 2. 尺寸计算
    image_height = calculate_image_height(display_data, footer_text)

    # 3. 初始化图片
    img = Image.new('RGBA', (IMAGE_WIDTH, image_height), color=CANVAS_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    # 4. 绘制页眉和背景
    _draw_header_and_background(draw, image_height, footer_text != "")

    # 5. 绘制所有服务器行
    list_start_y = LAYOUT_TITLE_AREA_HEIGHT + OFFSET_SERVER_LIST_START_Y
    server_index = 0
    active_server_offset_count = 0

    for i,server_data in enumerate(display_data):
        # 判断服务器类型（独立/主服/子服）
        info = server_data.get('data_manager_info', {})
        server_type = info.get('server_type', 'standalone')

        # 判断当前服务器是否为第一个子服
        is_first_child = False
        parent_had_player_list = False  # 新增：用于判断主服是否有玩家列表
        if server_type == 'child':
            # 检查前一个服务器是否不是子服
            if i > 0 and display_data[i - 1].get('data_manager_info', {}).get('server_type') != 'child':
                is_first_child = True
                # 检查主服（前一个服务器）是否有玩家列表
                parent_server_data = display_data[i - 1]
                parent_player_sample = parent_server_data.get('players', {}).get('sample')
                if parent_server_data.get('online') and parent_server_data.get('players', {}).get(
                        'online') != 0 and parent_player_sample:
                    parent_had_player_list = True

        # 预判：下一个服务器是否还是子服？
        is_next_child = False
        if i + 1 < len(display_data):
            next_server = display_data[i + 1]
            next_info = next_server.get('data_manager_info', {})
            if next_info.get('server_type', 'standalone') == 'child':
                is_next_child = True

        # 计算子服水平偏移量
        horizontal_offset = CHILD_INDENT_PX if server_type == 'child' else 0

        # 计算当前行的起始 Y 坐标
        current_y = list_start_y + server_index * SERVER_ROW_HEIGHT + active_server_offset_count * PLAYER_LIST_OFFSET

        # 调用独立的绘制函数
        await _draw_server_row(img, draw, server_data, current_y, horizontal_offset,server_type, is_next_child,is_first_child,parent_had_player_list)

        # 维护活跃服务器的偏移计数器
        player_sample = server_data.get('players', {}).get('sample')
        if server_data.get('online') and server_data.get('players', {}).get('online') != 0 and player_sample:
            active_server_offset_count += 1

        server_index += 1

    # 6. 绘制页脚和 Credit
    _draw_footer_and_credit(draw, image_height, footer_text)

    # 7. 保存并返回路径
    img_path = os.path.join(SAVE_IMG_DIR, f"mc_status_{group_id}.png")
    img.save(img_path)
    return img_path


def calculate_image_height(display_data: List[Dict[str, Any]], footer_text: str) -> int:
    """
    根据服务器列表和页脚内容计算最终图片的总高度。
    """
    # 使用常量，提高可读性
    from .constants import LAYOUT_TITLE_AREA_HEIGHT, LAYOUT_CREDIT_AREA_HEIGHT, LAYOUT_FOOTER_AREA_HEIGHT, \
        SERVER_ROW_HEIGHT, PLAYER_LIST_OFFSET

    # 步骤 1: 统计活跃服务器数量
    active_server_count = get_active_server_count(display_data)

    # 累加高度
    current_y = LAYOUT_TITLE_AREA_HEIGHT  # 顶部标题区域
    current_y += len(display_data) * SERVER_ROW_HEIGHT
    current_y += active_server_count * PLAYER_LIST_OFFSET # 活跃玩家信息行

    # 底部区域
    if footer_text:
        current_y += LAYOUT_FOOTER_AREA_HEIGHT
    current_y += LAYOUT_CREDIT_AREA_HEIGHT

    return current_y


async def _draw_server_row(img: Image.Image, draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int,
                           horizontal_offset: int,server_type: str, is_next_child: bool, is_first_child: bool,parent_had_player_list: bool):
    """
    绘制单个服务器条目（图标、MOTD、IP、状态、玩家列表）和连接线。
    """
    # 这一步负责绘制 MOTD/Icon/IP/Ping/Players/Version/PlayerList
    info = server_data.get('data_manager_info', {})
    tag = info.get('tag')
    tag_color_hex = info.get('tag_color')  # tagの背景色

    if server_type == 'child':
        # 只有子服需要绘制连接线
        _draw_connector_line(draw, current_y, is_next_child, is_first_child, parent_had_player_list)

    # 1. 绘制图标
    await _draw_icon(img, server_data, current_y, horizontal_offset)

    # 2. 绘制 Tag
    tag_total_width = _draw_tag_with_background(draw, tag, tag_color_hex, current_y, horizontal_offset)

    # 3. 绘制标题（MOTD）
    _draw_motd(draw, server_data, current_y, horizontal_offset, tag_total_width)

    # 4. 绘制IP/域名
    _draw_hostname(draw, server_data, current_y, horizontal_offset)

    # 5. 绘制状态信息（Ping/Players/Version/Active Player List）
    _draw_status_info(draw, server_data, current_y)

def _draw_header_and_background(draw: ImageDraw.ImageDraw, image_height: int, footer_exists: bool):
    """
    绘制背景矩形和居中标题。
    """
    from .constants import LAYOUT_TITLE_AREA_HEIGHT, LAYOUT_CREDIT_AREA_HEIGHT, LAYOUT_FOOTER_AREA_HEIGHT, \
        MAIN_CONTENT_BACKGROUND_COLOR, IMAGE_WIDTH, PRIMARY_TEXT_COLOR
    from .fonts import FONT_MC_TITLE

    # 绘制中间的深色背景
    content_end_y = image_height - LAYOUT_CREDIT_AREA_HEIGHT
    if footer_exists:
        content_end_y -= LAYOUT_FOOTER_AREA_HEIGHT

    draw.rectangle(xy=(0, LAYOUT_TITLE_AREA_HEIGHT, IMAGE_WIDTH, content_end_y),
                   fill=MAIN_CONTENT_BACKGROUND_COLOR)

    # 居中绘制标题
    title_text = "Minecraft服务器状态"
    draw.text(xy=(IMAGE_WIDTH / 2, LAYOUT_TITLE_AREA_HEIGHT / 2),
              text=title_text,
              fill=PRIMARY_TEXT_COLOR,
              font=FONT_MC_TITLE,
              anchor='mm')


def _draw_footer_and_credit(draw: ImageDraw.ImageDraw, image_height: int, footer_text: str):
    """
    绘制页脚文本和 Credit 文本。
    """
    from .constants import LAYOUT_BASE_PADDING, LAYOUT_CREDIT_AREA_HEIGHT, LAYOUT_FOOTER_AREA_HEIGHT, \
        PRIMARY_TEXT_COLOR, CREDIT_TEXT_COLOR
    from .fonts import FONT_MC_MEDIUM, FONT_ZH_CREDIT

    # 绘制页脚 (Footer)
    if footer_text:
        footer_y = image_height - LAYOUT_CREDIT_AREA_HEIGHT - (LAYOUT_FOOTER_AREA_HEIGHT / 2)
        draw.text((LAYOUT_BASE_PADDING, footer_y),
                  text=footer_text,
                  anchor="lm",
                  fill=PRIMARY_TEXT_COLOR,
                  font=FONT_MC_MEDIUM)

    # 绘制 Credit
    credit_y = image_height - (LAYOUT_CREDIT_AREA_HEIGHT / 2)
    draw.text((IMAGE_WIDTH / 2, credit_y),
              "Powered by FlyingPig278, LITTLE-UNIkeEN",
              fill=CREDIT_TEXT_COLOR,
              font=FONT_ZH_CREDIT,
              anchor="mm")


async def _draw_icon(img: Image.Image, server_data: Dict[str, Any], current_y: int, horizontal_offset: int, ):
    """
    异步绘制服务器图标 (Favicon)。
    """
    icon_url = server_data.get("favicon")
    if icon_url:
        icon_bytes = await decode_image(icon_url)
        if icon_bytes:
            try:
                img_avatar = Image.open(icon_bytes).resize((LAYOUT_SERVER_ICON_SIZE, LAYOUT_SERVER_ICON_SIZE))
                img_avatar = img_avatar.convert("RGBA")
                img.paste(img_avatar, (horizontal_offset + LAYOUT_BASE_PADDING, current_y), img_avatar)
            except Exception as e:
                print(f"Failed to paste server icon: {e}")


def _draw_tag_with_background(draw: ImageDraw.ImageDraw, tag: str, tag_color_hex: str, current_y: int,
                              horizontal_offset: int) -> int:
    """
    绘制带背景色的服务器 Tag 标签，并返回标签的总宽度。
    """
    if not tag:
        return 0

    # 1. 确定颜色和Tag内容
    # 默认背景色（如果未设置颜色或颜色无效）
    fill_color = TAG_DEFAULT_BACKGROUND
    if tag_color_hex:
        try:
            # 假设 tag_color_hex 是一个干净的 RRGGBB 字符串
            fill_color = f"#{tag_color_hex}"
        except Exception:
            # 颜色解析失败，使用默认灰色
            pass

    tag_text = tag

    # 2. 计算 Tag 尺寸和位置
    # tag_text_width, tag_text_height = FONT_MC_MOTD.getsize(tag_text)
    bbox = draw.textbbox((0, 0), tag_text, font=FONT_ZH_TAG)
    tag_text_height = bbox[3] - bbox[1]
    tag_text_width = bbox[2] - bbox[0]

    # Tag 矩形的总尺寸
    rect_width = tag_text_width + 2 * TAG_PADDING_X
    rect_height = tag_text_height + 2 * TAG_PADDING_Y

    # Tag 的起始 X 坐标 (紧跟 Icon 之后)
    tag_start_x = horizontal_offset + LAYOUT_BASE_PADDING + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING

    # Tag 矩形的四个坐标
    x0 = tag_start_x
    y0 = current_y  # 垂直居中
    x1 = x0 + rect_width
    y1 = y0 + rect_height

    # 3. 绘制背景矩形 (Tag 背景)
    draw.rounded_rectangle(xy=(x0, y0, x1, y1), fill=fill_color, radius=3)  # 稍微圆角

    # 4. 绘制 Tag 文本 (在矩形中心)
    center_x = x0 + rect_width / 2
    center_y = y0 + rect_height / 2

    draw.text(xy=(center_x, center_y),
              text=tag_text,
              fill=TAG_TEXT_COLOR,
              font=FONT_ZH_TAG,
              anchor='mm')  # 中心对齐

    # 返回标签总宽度，用于 MOTD 偏移
    # Tag 总宽度 = 矩形宽度 + 矩形与 MOTD 之间的间距
    return rect_width + ICON_TEXT_SPACING

def _draw_motd(draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int, horizontal_offset: int, tag_total_width: int = 0):
    """
    解析、截断并绘制服务器的 MOTD 标题（支持 Minecraft 和 HTML 颜色码）。
    """
    # 绘制标题
    motd_text = "未获取到MOTD"
    description_data = server_data.get("description")
    motd_start_x = horizontal_offset + LAYOUT_BASE_PADDING + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING + tag_total_width

    # 获取title，并做初步处理。然后绘制
    if isinstance(description_data, dict):
        title = description_data.get('html') or description_data.get('text', 'Unknown Server Name')

        title = title.replace('服务器已离线...', '')
        check_title = title.replace('<br>', ' | ')

        is_html_mode = description_data.get('html', False)  # 获取是否为 HTML 模式
        rendered_length = calculate_clean_length(check_title, FONT_MC_MOTD, is_html=is_html_mode) + horizontal_offset

        # 最大长度为 title 起始处至 ping 前
        if rendered_length <= IMAGE_WIDTH - 2 * LAYOUT_BASE_PADDING - LAYOUT_SERVER_ICON_SIZE - ICON_TEXT_SPACING - draw.textlength(
                "9999ms", font=FONT_MC_MEDIUM):
            final_title = check_title  # 情况 A: 未超长，使用完整连接后的标题
        else:  # 情况 B: 超长，只截取第一个查询地址
            # 截取 <br> 之前的部分
            truncated_title = title.split('<br>', 1)[0]
            # 将截取后的部分赋值为最终标题
            final_title = truncated_title

        # 处理HTML
        if is_html_mode:
            draw_colored_title_html(draw, final_title,
                                    (motd_start_x,
                                     current_y), font=FONT_MC_MOTD)
        else:
            # 处理Minecraft颜色码
            final_title = re.sub(r'§[klmno]', '', final_title)
            draw_colored_title(draw, final_title,
                               (motd_start_x,
                                current_y), font=FONT_MC_MOTD)
    else:  # 未获取到motd （为什么会出现这种情况呢？）
        draw_colored_title(draw, motd_text,
                           (motd_start_x, current_y),
                           font=FONT_MC_MOTD)


def _draw_hostname(draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int, horizontal_offset: int, ):
    """
    格式化并绘制服务器的 IP/域名。
    """
    hostname = server_data.get('original_query', '未知服务器').replace('.', ' . ').replace(':', " : ").replace('|',
                                                                                                               '   |   ')
    draw.text((horizontal_offset + LAYOUT_BASE_PADDING + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING, current_y + OFFSET_IP_Y),
              hostname, fill=SECONDARY_TEXT_COLOR, font=FONT_MC_MEDIUM)


def _draw_status_info(draw: ImageDraw.ImageDraw, server_data: Dict[str, Any], current_y: int, ):
    """
    绘制右侧所有状态信息（Ping, 玩家数, 版本, 活跃玩家列表）。
    """
    if server_data.get('online'):  # 对在线服务器
        # 处理ping值
        ping = int(server_data.get('ping', 0))
        ping_color = PING_COLOR_RED if ping >= 100 else PING_COLOR_GREEN
        ping_text = f"{ping}ms"
        # 绘制ping值
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y), ping_text, fill=ping_color, anchor='ra',
                  font=FONT_MC_MEDIUM)

        # 处理玩家数
        players_text = f"{server_data.get('players', {}).get('online', 'N/A')}/{server_data.get('players', {}).get('max', 'N/A')}"
        # 绘制玩家数
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_PLAYER_COUNT_Y), players_text,
                  fill=SECONDARY_TEXT_COLOR, anchor='ra', font=FONT_MC_MEDIUM)

        # 处理游戏版本信息
        version_text = server_data.get('version', 'N/A')
        # 绘制游戏版本信息
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_VERSION_Y), version_text,
                  fill=SECONDARY_TEXT_COLOR, anchor='ra', font=FONT_MC_MEDIUM)

        # 要求服务器有在线人数，且有在线玩家信息。
        player_sample = server_data.get('players', {}).get('sample')
        if server_data.get('players', {}).get('online') != 0 and player_sample:
            try:
                player_names_accumulator = ""
                for player in player_sample:
                    player_name = player['name']
                    # 加入一个玩家
                    potential_text = player_names_accumulator + (' ,  ' if player_names_accumulator else "") + player_name
                    # 检查新文本的长度是否超出限制（显示至ICON右侧为止）
                    if draw.textlength(potential_text,
                                       font=FONT_MC_SMALL) >= IMAGE_WIDTH - LAYOUT_BASE_PADDING * 2 - LAYOUT_SERVER_ICON_SIZE - draw.textlength(
                            '●', font=FONT_MC_SMALL):
                        # 超出限制，中断循环
                        if player_names_accumulator:
                            # 如果已经添加了至少一个玩家的名字，添加 "等" 字样，然后中断
                            player_names = player_names_accumulator + "等"
                        else:
                            # 如果第一个玩家的名字就超出了限制（这种情况很少），则只显示他
                            player_names = player_name + "等"
                        break
                    # 没有超出限制，将玩家名字加入累积器
                    player_names_accumulator = potential_text
                else:  # 循环正常终止，所有玩家名字均未超长
                    player_names = player_names_accumulator
                player_text = f"{player_names} 正在游玩"

            except (KeyError, TypeError):
                player_text = "( 玩家信息获取失败qwq )"

            draw.text(xy=(IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_PLAYER_LIST_Y),
                      text='●',
                      fill=PING_COLOR_GREEN,
                      anchor='ra',
                      font=FONT_MC_SMALL,
                      )
            draw.text(
                xy=(IMAGE_WIDTH - LAYOUT_BASE_PADDING - draw.textlength('●', font=FONT_MC_SMALL) - PLAYER_LIST_DOT_SPACING, current_y + OFFSET_PLAYER_LIST_Y),
                text=player_text,
                fill=SECONDARY_TEXT_COLOR,
                anchor='ra',
                font=FONT_MC_SMALL,
                )
    else:
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y),
                  text="offline",
                  fill=PING_COLOR_RED,
                  anchor='ra',
                  font=FONT_MC_MEDIUM)
        draw.text((IMAGE_WIDTH - LAYOUT_BASE_PADDING, current_y + OFFSET_PLAYER_COUNT_Y),
                  text="服务器离线",
                  fill=SECONDARY_TEXT_COLOR,
                  anchor='ra',
                  font=FONT_MC_MEDIUM
                  )


def _draw_connector_line(draw: ImageDraw.ImageDraw, current_y: int, extend_down: bool, is_first_child: bool, parent_had_player_list: bool):
    """
    绘制连接子服到主服的 L 形连接线。

    Args:
        draw (ImageDraw.ImageDraw): 绘图对象。
        current_y (int): 当前行的起始 Y 坐标。
        extend_down (bool): 下一个服务器是否为子服，决定垂直线是否向下延伸。
        is_first_child (bool): 当前是否为第一个子服。
        parent_had_player_list (bool): (仅当 is_first_child=True 时有效)主服是否带有玩家列表。
    """
    # 1. 定义关键尺寸和坐标
    # 主干垂直线的 X 坐标 (与主服图标中心对齐)
    vertical_line_x = LAYOUT_BASE_PADDING + (LAYOUT_SERVER_ICON_SIZE / 2)
    # 当前子服图标中心的 Y 坐标
    child_icon_center_y = current_y + (LAYOUT_SERVER_ICON_SIZE / 2)
    # 子服图标左侧的 X 坐标
    child_icon_x = LAYOUT_BASE_PADDING + CHILD_INDENT_PX

    # 2. 绘制水平线（连接主干和子服图标）
    draw.line(
        xy=(vertical_line_x, child_icon_center_y, child_icon_x, child_icon_center_y),
        fill=CONNECTOR_LINE_COLOR,
        width=CONNECTOR_LINE_THICKNESS
    )

    # 3. 根据是否为第一个子服，使用不同逻辑绘制垂直线
    if is_first_child:
        # 【核心逻辑】对于第一个子服，竖线连接主服中心和当前子服中心
        # a. 基于当前子服的 Y 坐标，反向计算出主服的起始 Y 坐标
        parent_row_y_start = current_y - SERVER_ROW_HEIGHT
        if parent_had_player_list:
            parent_row_y_start -= PLAYER_LIST_OFFSET  # 如果主服有玩家列表，需要减去额外的高度

        # b. 计算出主服图标的中心 Y 坐标
        # parent_icon_center_y = parent_row_y_start + (LAYOUT_SERVER_ICON_SIZE / 2)
        parent_icon_center_y = parent_row_y_start + LAYOUT_SERVER_ICON_SIZE

        # c. 绘制从主服中心到子服中心的垂直线
        draw.line(
            xy=(vertical_line_x, parent_icon_center_y, vertical_line_x, child_icon_center_y),
            fill=CONNECTOR_LINE_COLOR,
            width=CONNECTOR_LINE_THICKNESS
        )

        # d. 如果下方还有子服，需要额外画一条从当前图标中心延伸到行底部的线
        if extend_down:
            draw.line(
                xy=(vertical_line_x, child_icon_center_y, vertical_line_x, current_y + SERVER_ROW_HEIGHT),
                fill=CONNECTOR_LINE_COLOR,
                width=CONNECTOR_LINE_THICKNESS
            )
    else:
        # 对于后续的子服，逻辑不变：从行顶连接到行中或行底
        y_start = current_y
        y_end = current_y + SERVER_ROW_HEIGHT if extend_down else child_icon_center_y
        if y_end > y_start:
            draw.line(
                xy=(vertical_line_x, y_start, vertical_line_x, y_end),
                fill=CONNECTOR_LINE_COLOR,
                width=CONNECTOR_LINE_THICKNESS
            )