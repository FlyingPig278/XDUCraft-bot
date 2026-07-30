# -*- coding: utf-8 -*-

"""状态图片的视觉令牌。

设计语言来自 ``koishi-plugin-mcsm-portal``，规则只有几条，但每条都是硬约束：

1. **逻辑坐标 = Minecraft 原版窗口宽度 854。** 所有尺寸都用逻辑单位书写，
   出图时统一乘 :data:`SCALE`。这等价于参考项目的 ``deviceScaleFactor``：
   整数倍放大，像素字体不会糊。
2. **零圆角。** 所有边框都是 2 逻辑像素的实心直角边。
3. **不发明配色。** 背景是方块材质平铺 + 一层纯黑压暗，卡片只用黑白透明度
   分层；有彩色的地方只有两处——右栏的状态色取自 Minecraft 自己的聊天调色板，
   左边条的验证方式色来自 :mod:`.auth_mode`（学校的身份色，不能改）。
4. **色相分区。** 状态色只出现在右栏，验证方式色只出现在左边条，两者永不同框，
   所以绿色永远只表示“延迟低”，不会和“正版登录”的绿撞含义。
5. **字号必须落在字体的像素网格上**，见 :mod:`.fonts` 的说明。
"""

from .constants import MINECRAFT_COLOR_CODES
from .settings import SETTINGS

# ==============================================================================
# 1. 缩放
# ==============================================================================

#: 逻辑画布宽度。854×480 是 Minecraft 的默认窗口尺寸，参考项目直接拿它当画布。
#: 由 ``MCS_WIDTH`` 配置，import 时读取一次——:mod:`.fonts` 的字号在 import 阶段
#: 就按倍率算好了，运行期再改会让字号和画布对不上。改这两项要重启。
CANVAS_WIDTH = SETTINGS.width
#: 画布最小高度，同样取自原版窗口。``MCS_MIN_HEIGHT=0`` 表示收缩到内容。
CANVAS_MIN_HEIGHT = SETTINGS.min_height

#: 逻辑单位 -> 物理像素的倍率。只能是偶数，否则像素字体会偏离网格被插值糊掉，
#: 具体推导见 :func:`.settings.normalize_scale`。
SCALE = SETTINGS.scale


def px(value: float) -> int:
    """逻辑单位换算成物理像素。"""
    return int(round(value * SCALE))


# ==============================================================================
# 2. 配色
# ==============================================================================

# --- 中性层：全部是黑/白 + 透明度，叠在材质背景上 ---
#: 没有材质时的兜底压暗层，参考项目用的是 rgba(0,0,0,.58)。
#: 有材质时压多少黑由 :func:`.raster.texture_scrim` 按材质亮度算，不是定值——
#: 竹板砖比泥土亮得多，泥土又比黑色混凝土粉末亮得多，一刀切会让亮材质上的字发飘。
SCRIM = (0, 0, 0, 148)
#: 所有较亮材质压到与黑色混凝土粉末接近的相对亮度。黑色叠层无法提亮少数
#: 更暗的纹理，但全库压暗后的亮度差从约 100 倍收敛到约 1.5 倍。
SCRIM_TARGET_LUMINANCE = 0.012
#: 再亮的材质也保留最低限度的纹理。
SCRIM_MAX_ALPHA = 0.96
#: 在线卡片底色 rgba(0,0,0,.40)。
SURFACE = (0, 0, 0, 102)
#: 离线卡片不铺底——“暗”本身就是离线的信号，不需要再加一个颜色。
SURFACE_IDLE = (0, 0, 0, 0)
#: 顶栏 / 底栏的通栏底色 rgba(0,0,0,.60)。
BAND = (0, 0, 0, 153)
#: 唯一的边框色 rgba(255,255,255,.20)。
RULE = (255, 255, 255, 51)
#: 通栏之间的深色分隔 rgba(0,0,0,.30)。
RULE_DARK = (0, 0, 0, 77)
#: 版本号等小胶片的底色 rgba(255,255,255,.15)。
CHIP = (255, 255, 255, 38)

#: 边框宽度。整套设计里只有这一个值，没有第二种粗细。
RULE_WIDTH = 2

# --- 文字：同一个白，靠透明度分层级 ---
INK = (255, 255, 255, 255)
INK_STRONG = (255, 255, 255, 217)   # .85
INK_MUTED = (255, 255, 255, 191)    # .75
INK_FAINT = (255, 255, 255, 178)    # .70
INK_GHOST = (255, 255, 255, 128)    # .50

#: 浅底胶片上的深色文字（Tag 底色很亮时用）。
INK_DARK = (0, 0, 0, 255)
#: 黑字 / 白字由 WCAG 对比度决定，见 :func:`.raster.ink_for_background`。
#: 这里没有阈值可调——加阈值就意味着允许它选中可读性更差的一边。

# --- 状态色：直接引用 Minecraft 聊天调色板，不另造颜色 ---
STATE_EXCELLENT = MINECRAFT_COLOR_CODES["a"]  # §a #55FF55
STATE_GOOD = MINECRAFT_COLOR_CODES["e"]       # §e #FFFF55
STATE_FAIR = MINECRAFT_COLOR_CODES["6"]       # §6 #FFAA00
STATE_POOR = MINECRAFT_COLOR_CODES["c"]       # §c #FF5555
STATE_DEAD = MINECRAFT_COLOR_CODES["7"]       # §7 #AAAAAA

#: 延迟分档（毫秒）。保留原设计 100 / 200 的判断口径，另外补两档，
#: 让 5 格信号条有足够的分辨率。
PING_TIER_THRESHOLDS = (100, 200, 400)
#: 信号条格数。
SIGNAL_BARS = 5

#: 仅按配置显示（未经实测确认）的左边条画成虚线。
#: 以前是把实色降到 150 的不透明度，但"这条边比那条边淡一点"没法自解释——
#: 得先在图例里写一行字教人怎么读。虚线本身就是"待定/未证实"的通用记号，
#: 不需要注解，图例因此少一行。
AUTH_DASH = 8
AUTH_DASH_GAP = 6
#: 配置与实测冲突时，边条上叠一道警示色。
AUTH_CONFLICT_COLOR = STATE_FAIR

# ==============================================================================
# 3. 排版（逻辑单位；换算与网格约束见 fonts.py）
# ==============================================================================

TYPE_EYEBROW = 12    # 顶栏品牌行
TYPE_TITLE = 36      # 图片主标题
TYPE_SUBTITLE = 12   # 顶栏副标题（时间 + 数据源）
TYPE_CHIP = 12       # 顶栏右侧概览胶片 / 卡片 Tag
TYPE_MOTD = 16       # 卡片 MOTD，两行；放大填满标题与地址之间的文字区
TYPE_ADDRESS = 12    # 地址行
TYPE_MICRO = 8       # 玩家名、署名、版本号
#: 数字用等宽体 Monocraft。它本身带抗锯齿、不受像素网格约束，但缺中日韩字形，
#: 混进中文时会回退到正文体——所以字号仍必须落在正文体的 8px 网格上。
TYPE_DATA = 12       # 右栏三行：延迟 / 人数 / 版本号，三者同字号
TYPE_LABEL = 12      # 离线等状态词

#: 方块单位。材质是 16×16 的方块贴图，所有结构性间距都按它的整数倍走。
BLOCK = 8

PAGE_PADDING_X = 32
PAGE_PADDING_TOP = 24
PAGE_PADDING_BOTTOM = 20

#: 背景材质平铺尺寸。
TEXTURE_TILE = 64

#: 大块之间的留白。顶栏与列表、列表与底部区域都靠它隔开，不能贴在一起。
SECTION_GAP = 24

# --- 顶栏 ---
HEADER_GAP = 14
#: 两组纯文字在线概览之间的间距。
HEADER_STATUS_GAP = 8

# --- 图例（验证方式色板）。在底栏**外面**，铺在材质背景上。---
LEGEND_HEIGHT = 30
LEGEND_SWATCH = 12
LEGEND_GAP = 16

# --- 底栏：群公告和署名同在一块深色通栏里 ---
BAND_PADDING_Y = 12
#: 群公告行高。没有公告时这一行不占高度。
BAND_NOTICE_HEIGHT = 22
BAND_CREDIT_HEIGHT = 18
BAND_LINE_GAP = 6
#: 底栏用渐变压角代替硬边通栏：从这个高度开始由全透明渐变到 BAND。
BAND_VIGNETTE = 56
#: 渐变底端的黑。比 BAND 更实一点——渐变上半段几乎是透明的，底端得压得住。
BAND_BOTTOM = (0, 0, 0, 205)

# --- 卡片 ---
#: 精简卡片只保留两行 MOTD；80px 高度让 64px 图标与四边保持 8px 内边距。
CARD_HEIGHT = 80
CARD_GAP = 4
CARD_PAD = 8
CARD_COL_GAP = 12
ICON_SIZE = CARD_HEIGHT - 2 * CARD_PAD
MOTD_LINES = 2
RAIL_WIDTH = 156

#: 左边条：承载验证方式颜色，是这套设计里唯一的彩色竖条。
AUTH_STRIPE_WIDTH = 4
#: Tag 移到右上角，整个胶片以延迟文本左边为右对齐锚点。
TAG_CHIP_PADDING_X = 8
TAG_CHIP_HEIGHT = 24
TAG_CHIP_MAX_WIDTH = 96
TAG_STATUS_GAP = 8

#: 子服务器缩进 = 4 个方块单位。
CHILD_INDENT = BLOCK * 4
#: 父子连线用 2×2 的像素点阵画，不用实线——直线在像素语境里太“矢量”了。
SPINE_DOT = 2
SPINE_GAP = 2

__all__ = [
    "CANVAS_WIDTH", "CANVAS_MIN_HEIGHT", "SCALE", "px",
    "SCRIM", "SCRIM_TARGET_LUMINANCE", "SCRIM_MAX_ALPHA", "SURFACE", "SURFACE_IDLE", "BAND", "RULE", "RULE_DARK", "CHIP", "RULE_WIDTH",
    "INK", "INK_STRONG", "INK_MUTED", "INK_FAINT", "INK_GHOST", "INK_DARK",
    "STATE_EXCELLENT", "STATE_GOOD", "STATE_FAIR", "STATE_POOR", "STATE_DEAD",
    "PING_TIER_THRESHOLDS", "SIGNAL_BARS",
    "AUTH_DASH", "AUTH_DASH_GAP", "AUTH_CONFLICT_COLOR",
    "TYPE_EYEBROW", "TYPE_TITLE", "TYPE_SUBTITLE", "TYPE_CHIP",
    "TYPE_MOTD", "TYPE_ADDRESS", "TYPE_MICRO", "TYPE_DATA", "TYPE_LABEL",
    "BLOCK", "PAGE_PADDING_X", "PAGE_PADDING_TOP", "PAGE_PADDING_BOTTOM", "TEXTURE_TILE",
    "SECTION_GAP", "HEADER_GAP", "HEADER_STATUS_GAP",
    "LEGEND_HEIGHT", "LEGEND_SWATCH", "LEGEND_GAP",
    "BAND_PADDING_Y", "BAND_NOTICE_HEIGHT", "BAND_CREDIT_HEIGHT", "BAND_LINE_GAP",
    "BAND_VIGNETTE", "BAND_BOTTOM",
    "CARD_HEIGHT", "CARD_GAP", "CARD_PAD", "CARD_COL_GAP",
    "ICON_SIZE", "MOTD_LINES", "RAIL_WIDTH",
    "AUTH_STRIPE_WIDTH",
    "TAG_CHIP_PADDING_X", "TAG_CHIP_HEIGHT", "TAG_CHIP_MAX_WIDTH", "TAG_STATUS_GAP",
    "CHILD_INDENT", "SPINE_DOT", "SPINE_GAP",
]
