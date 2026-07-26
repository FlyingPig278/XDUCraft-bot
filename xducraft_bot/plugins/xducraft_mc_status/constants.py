# -*- coding: utf-8 -*-

"""状态图片的全部视觉常量。

改这里就能调整最终图片的样式，不需要动绘图逻辑。

布局采用**卡片式**：每台服务器是一张圆角卡片，卡片内部的坐标都是相对卡片
左上角的偏移量，这样调整卡片高度时不用逐个改绝对坐标。
"""

import os

# ==============================================================================
# 1. 核心路径
# ==============================================================================

_current_dir = os.path.dirname(__file__)

FONTS_PATH = os.path.join(_current_dir, "resources", "fonts")
DEFAULT_SERVER_ICON_PATH = os.path.join(_current_dir, "resources", "images", "default_server_icon.png")
OFFLINE_SERVER_ICON_PATH = os.path.join(_current_dir, "resources", "images", "offline_server_icon.png")
SAVE_IMG_DIR = os.path.join(_current_dir, "data", "images")

# ==============================================================================
# 2. 配色
# ==============================================================================

# --- 画布 ---
CANVAS_BACKGROUND_COLOR = (28, 23, 18, 255)      # 最底层背景
HEADER_TOP_COLOR = (58, 42, 29, 255)             # 顶部标题栏渐变起点
HEADER_BOTTOM_COLOR = (36, 28, 21, 255)          # 顶部标题栏渐变终点
MAIN_CONTENT_BACKGROUND_COLOR = (20, 16, 12, 255)  # 列表区底色

# --- 卡片 ---
CARD_BACKGROUND_COLOR = (33, 27, 21, 255)          # 在线服务器卡片
CARD_BACKGROUND_OFFLINE_COLOR = (26, 23, 21, 255)  # 离线服务器卡片（更暗更灰）
CARD_BORDER_COLOR = (56, 46, 35, 255)
CARD_BORDER_OFFLINE_COLOR = (44, 39, 35, 255)
CARD_RADIUS = 10
#: 卡片左侧的状态条：一眼区分在线/离线
CARD_ACCENT_WIDTH = 5
CARD_ACCENT_ONLINE_COLOR = (76, 200, 96, 255)
CARD_ACCENT_OFFLINE_COLOR = (128, 92, 84, 255)

# --- 文字 ---
PRIMARY_TEXT_COLOR = (255, 255, 255, 255)
SECONDARY_TEXT_COLOR = (176, 168, 156, 255)   # 比旧值稍暖，深底上对比度更好
MUTED_TEXT_COLOR = (128, 120, 110, 255)
OFFLINE_TEXT_COLOR = (140, 128, 120, 255)
CREDIT_TEXT_COLOR = (120, 112, 102, 255)
HEADER_SUBTITLE_COLOR = (196, 176, 148, 255)

# --- 状态色 ---
PING_COLOR_GREEN = (86, 211, 100, 255)    # < 100ms
PING_COLOR_YELLOW = (232, 190, 74, 255)   # 100 ~ 200ms
PING_COLOR_RED = (240, 104, 96, 255)      # >= 200ms 或离线
PING_THRESHOLD_GOOD = 100
PING_THRESHOLD_FAIR = 200

PLAYER_ONLINE_DOT_COLOR = (86, 211, 100, 255)

# --- 组件 ---
TAG_DEFAULT_BACKGROUND = "#3A3A3A"
TAG_TEXT_COLOR = (255, 255, 255, 255)
TAG_TEXT_BRIGHTNESS_THRESHOLD = 186  # 感知亮度 >= 此值视为浅底，改用深色文字
CONNECTOR_LINE_COLOR = (92, 78, 62, 255)

# --- MOTD 颜色代码 ---
MINECRAFT_COLOR_CODES = {
    "0": (0, 0, 0, 255), "1": (0, 0, 170, 255), "2": (0, 170, 0, 255), "3": (0, 170, 170, 255),
    "4": (170, 0, 0, 255), "5": (170, 0, 170, 255), "6": (255, 170, 0, 255), "7": (170, 170, 170, 255),
    "8": (85, 85, 85, 255), "9": (85, 85, 255, 255), "a": (85, 255, 85, 255), "b": (85, 255, 255, 255),
    "c": (255, 85, 85, 255), "d": (255, 85, 255, 255), "e": (255, 255, 85, 255), "f": (255, 255, 255, 255),
    "r": (255, 255, 255, 255),
}

HTML_COLOR_CODES = {
    "black": (0, 0, 0, 255), "dark_blue": (0, 0, 170, 255), "dark_green": (0, 170, 0, 255),
    "dark_aqua": (0, 170, 170, 255), "dark_red": (170, 0, 0, 255), "dark_purple": (170, 0, 170, 255),
    "gold": (255, 170, 0, 255), "gray": (170, 170, 170, 255), "dark_gray": (85, 85, 85, 255),
    "blue": (85, 85, 255, 255), "green": (85, 255, 85, 255), "aqua": (85, 255, 255, 255),
    "red": (255, 85, 85, 255), "light_purple": (255, 85, 255, 255), "yellow": (255, 255, 85, 255),
    "white": (255, 255, 255, 255),
}

# ==============================================================================
# 3. 布局
# ==============================================================================

IMAGE_WIDTH = 1200
LAYOUT_BASE_PADDING = 48          # 卡片距画布左右边缘
LAYOUT_TITLE_AREA_HEIGHT = 150    # 顶部标题+概览栏
LAYOUT_LEGEND_AREA_HEIGHT = 62    # 验证方式图例栏（无徽章时不占高度）
LAYOUT_FOOTER_AREA_HEIGHT = 62    # 自定义页脚
LAYOUT_CREDIT_AREA_HEIGHT = 56    # 底部署名

OFFSET_SERVER_LIST_START_Y = 22   # 列表区顶部留白

# --- 卡片 ---
CARD_HEIGHT = 128                 # 基础卡片高度
CARD_GAP = 12                     # 卡片之间的垂直间距
PLAYER_ROW_EXTRA_HEIGHT = 36      # 有“正在游玩”一行时额外增加的高度
CHILD_INDENT_PX = 88              # 子服务器的水平缩进

#: 兼容旧调用：一整行（卡片 + 间距）占用的高度。
SERVER_ROW_HEIGHT = CARD_HEIGHT + CARD_GAP
PLAYER_LIST_OFFSET = PLAYER_ROW_EXTRA_HEIGHT

# --- 卡片内部（相对卡片左上角）---
CARD_PADDING_X = 18
LAYOUT_SERVER_ICON_SIZE = 76
CARD_ICON_OFFSET_Y = 26
ICON_TEXT_SPACING = 20
#: 图标右侧的文本起始 x
CARD_TEXT_OFFSET_X = CARD_PADDING_X + LAYOUT_SERVER_ICON_SIZE + ICON_TEXT_SPACING

OFFSET_MOTD_CENTER_Y = 46         # 第一行：Tag + MOTD
OFFSET_IP_CENTER_Y = 90           # 第二行：IP + 验证方式徽章
OFFSET_PLAYER_LIST_CENTER_Y = 146  # 展开的“正在游玩”行

#: 右侧信息列（右对齐，相对卡片右边缘）
OFFSET_PING_CENTER_Y = 38
OFFSET_PLAYER_COUNT_CENTER_Y = 70
OFFSET_VERSION_CENTER_Y = 100
#: 右侧信息列预留的宽度，MOTD 截断时要避开。
#: 版本号（"Requires MC 1.8 / 1.21" 这类）是这一列里最长的，按它来定。
RIGHT_COLUMN_RESERVED_WIDTH = 230

# --- Tag 徽标 ---
TAG_PADDING_X = 12
TAG_PADDING_Y = 6
TAG_RADIUS = 4

# --- 验证方式徽章 ---
AUTH_BADGE_PADDING_X = 10
AUTH_BADGE_PADDING_Y = 5
AUTH_BADGE_RADIUS = 9
AUTH_BADGE_SPACING = 14           # 与左侧 IP 文本的间距
#: 未确认（仅按配置显示）的徽章降低不透明度，和实测确认的区分开
AUTH_BADGE_UNCONFIRMED_ALPHA = 150

# --- 其他 ---
PLAYER_LIST_DOT_SPACING = 8
CONNECTOR_LINE_THICKNESS = 2

# ==============================================================================
# 4. 逻辑默认值
# ==============================================================================

DEFAULT_SERVER_PRIORITY = 100

#: Web 编辑器地址，``/mcs edit`` 会拼上压缩后的配置生成链接。
WEB_UI_BASE_URL = "https://edit.flyingpig278.com/"

#: 生成的图片保留时长（秒）。超过就清掉，避免 data/images 无限增长。
RENDERED_IMAGE_TTL = 10 * 60

# ==============================================================================
# 5. 帮助文本
# ==============================================================================

USAGE_USER = """【查询】
/mcs — 查询本群在线服务器
/mcs all — 连同离线服务器一起显示
/mcs <IP> — 查询单个服务器
/mcs list — 查看已添加的服务器列表
/mcs auth — 查看各服务器的登录验证方式
/mcs help — 显示本帮助"""

USAGE_ADMIN = """【Web 编辑器（推荐）】
/mcs edit — 生成配置链接，在网页里拖拽编辑
  编辑完成后按页面提示，私聊机器人发送导入命令
---
【查询】
/mcs — 查询本群在线服务器
/mcs all — 连同离线服务器一起显示
/mcs <IP> — 查询单个服务器
/mcs list — 查看服务器列表
/mcs auth — 查看各服务器的登录验证方式
---
【服务器增删】
/mcs add <IP> — 添加服务器
/mcs remove <IP> — 移除服务器
---
【登录验证方式】
/mcs auth — 查看本群所有服务器的验证方式
/mcs auth set <IP> <验证方式> — 指定某台服务器的验证方式
/mcs auth clear <IP> — 改回自动探测
/mcs auth default <验证方式|clear> — 设置本群默认验证方式
/mcs auth detect on|off — 开关自动探测
  验证方式可填：正版 / MUA / 外置 / 离线 / 混合
---
【数据源】
/mcs source — 查看当前生效的查询源
/mcs source set <protocol|sjtu|jsu|custom|auto> — 设置本群查询源
/mcs source clear — 清除本群覆盖，回退全局
/mcs source global set|clear <...> — 设置/清除全局默认
/mcs api set|clear <url> — 配置自定义后端地址
/mcs api global set|clear <url> — 配置全局默认后端地址
---
【显示与开关】
/mcs set <IP> <属性> <值> — tag / tag_color / comment / display_name /
  auth_mode / hide_ip / ignore_in_list / priority
/mcs clear <IP> <属性> — 重置某个属性
/mcs footer <文本> — 设置图片页脚
/mcs footer clear — 清除页脚
/mcs quiet on|off — 管理指令回执是否走私聊（默认开，避免群里刷屏）
---
【排查】
/mcs diag — 查看本群配置与各数据源连通性
/mcs export_json — 私聊导出原始 JSON 配置
---
/mcs help — 显示本帮助"""
