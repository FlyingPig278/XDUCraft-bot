# -*- coding: utf-8 -*-

"""路径、颜色码表与逻辑默认值。

视觉令牌（配色、排版、间距）都搬到了 :mod:`.tokens`。留在这里的是三类和外观
无关的东西：资源路径、Minecraft 的颜色码对照表，以及命令帮助文本。
"""

import os

# ==============================================================================
# 1. 核心路径
# ==============================================================================

_current_dir = os.path.dirname(__file__)

FONTS_PATH = os.path.join(_current_dir, "resources", "fonts")
TEXTURES_PATH = os.path.join(_current_dir, "resources", "textures")
DEFAULT_SERVER_ICON_PATH = os.path.join(_current_dir, "resources", "images", "default_server_icon.png")
OFFLINE_SERVER_ICON_PATH = os.path.join(_current_dir, "resources", "images", "offline_server_icon.png")
FIRE_ICON_PATH = os.path.join(_current_dir, "resources", "images", "fire.png")
SAVE_IMG_DIR = os.path.join(_current_dir, "data", "images")

# ==============================================================================
# 2. Minecraft 颜色码
# ==============================================================================

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
# 3. 逻辑默认值
# ==============================================================================

DEFAULT_SERVER_PRIORITY = 100

#: Web 编辑器地址，``/mcs edit`` 会拼上压缩后的配置生成链接。
WEB_UI_BASE_URL = "https://edit.flyingpig278.com/"

#: 生成的图片保留时长（秒）。超过就清掉，避免 data/images 无限增长。
RENDERED_IMAGE_TTL = 10 * 60

# ==============================================================================
# 4. 帮助文本
# ==============================================================================

USAGE_USER = """【查询】
/mcs — 查询本群在线服务器
/mcs all — 连同离线服务器一起显示
/mcs <IP> — 查询单个服务器
/mcs [all|<IP>] texture=<材质> — 本次查询临时换背景（如 texture=dirt）
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
/mcs [all|<IP>] texture=<材质> — 本次查询临时换背景（如 texture=dirt）
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
/mcs auth clear <IP> — 清除单服配置并回退本群默认值
/mcs auth default <验证方式|clear> — 设置本群默认验证方式
/mcs auth detect on|off — 开关尽力而为的自动探测（默认关）
  验证方式可填：正版 / MUA / XDU / 外置 / 离线 / 混合
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
