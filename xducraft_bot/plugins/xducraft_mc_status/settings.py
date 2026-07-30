"""状态图的渲染选项。

对齐 ``koishi-plugin-mcsm-portal`` 的 ``image`` 配置块：标题、署名、背景材质、
画布宽度、缩放倍率、是否显示生成时间。参考项目那边是 Koishi 的 Schema，这边是
NoneBot 的插件配置，都写在部署配置里，改完重启生效。

写在 ``.env`` 里，例如::

    MCS_BRAND=XDUCRAFT
    MCS_TITLE=Minecraft 服务器状态
    MCS_TEXTURE=random
    MCS_MIN_HEIGHT=0

**为什么不放进 server_data.json。** 那个文件里放的是“哪个群有哪些服务器、走哪个
查询源”这类运营数据，管理员在群里用命令就能改。这里这些是部署期的外观设定，
整台机器人一套，不该按群分叉，也不该让任何一个群管理员改掉全局观感。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from nonebot.log import logger

# NoneBot 2.x 本身就硬依赖 pydantic，拿不到它整台机器人根本起不来，
# 所以这里不做 try/except——假兜底只会把真正的错误藏到更靠后的地方。
from pydantic import BaseModel

#: ``texture`` 填这个值时每次出图随机换一张方块材质，对齐参考项目的 ``__random__``。
RANDOM_TEXTURE = "random"
#: ``texture`` 填这个值时不铺材质，只留纯黑底。
NO_TEXTURE = "none"
#: ``texture`` 留空时按群号稳定挑一张：同一个群每次都是同一张背景。
PER_GROUP_TEXTURE = ""

DEFAULT_BRAND = "XDUCRAFT"
DEFAULT_TITLE = "Minecraft 服务器状态"
#: 支持 ``§`` 颜色码，和参考项目的 ``DEFAULT_COPYRIGHT_TEXT`` 一样。
DEFAULT_CREDIT = "Powered by §7FlyingPig278, LITTLE-UNIkeEN, and KrLite"
DEFAULT_CANVAS_WIDTH = 768


class Config(BaseModel):
    """NoneBot 插件配置。字段名就是 ``.env`` 里的键（不区分大小写）。"""

    #: 顶栏品牌行。留空则不画这一行。支持 ``§`` 颜色码。
    mcs_brand: str = DEFAULT_BRAND
    #: 图片主标题。留空则不画。支持 ``§`` 颜色码。
    mcs_title: str = DEFAULT_TITLE
    #: 底栏署名。留空则不画。支持 ``§`` 颜色码。
    mcs_credit: str = DEFAULT_CREDIT
    #: 底栏右侧是否显示生成时间。
    mcs_show_generated_at: bool = True

    #: 背景材质：具体文件名（``stone.png``）、``random``、``none``，
    #: 或留空按群号稳定挑选。
    mcs_texture: str = PER_GROUP_TEXTURE

    #: 更适合群聊移动端查看的默认逻辑宽度；仍可通过 MCS_WIDTH 覆盖。
    mcs_width: int = DEFAULT_CANVAS_WIDTH
    #: 逻辑单位到物理像素的倍率。只接受偶数，见 :func:`normalize_scale`。
    mcs_scale: int = 2
    #: 图片最小逻辑高度。``0`` 表示收缩到内容，不留空白。
    mcs_min_height: int = 480


@dataclass(frozen=True)
class RenderSettings:
    """规整之后、渲染代码真正使用的设置。"""

    brand: str = DEFAULT_BRAND
    title: str = DEFAULT_TITLE
    credit: str = DEFAULT_CREDIT
    show_generated_at: bool = True
    texture: str = PER_GROUP_TEXTURE
    width: int = DEFAULT_CANVAS_WIDTH
    scale: int = 2
    min_height: int = 480

    def evolve(self, **changes) -> "RenderSettings":
        """派生一份改了几项的副本，预览脚本用它试不同外观。"""
        return replace(self, **changes)


def normalize_width(value: int) -> int:
    """画布宽度，和参考项目一样夹在 640–1600 之间。"""
    try:
        return max(640, min(1600, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_CANVAS_WIDTH


def normalize_scale(value: int) -> int:
    """缩放倍率，只接受 2 或 4。

    参考项目跑在浏览器里，``deviceScaleFactor`` 随便取 1–4 都行。这里不行：
    倍率直接决定物理字号，而像素字体要求物理字号落在 8（正文体）和 12
    （中日韩点阵体）的整数倍上。逻辑字号都是 4 的倍数，所以只有**偶数**倍率
    能同时满足两个网格；奇数倍率会让一部分字号偏格，字形被插值糊掉。
    """
    try:
        scale = int(value)
    except (TypeError, ValueError):
        return 2
    if scale in (2, 4):
        return scale
    fallback = 4 if scale > 3 else 2
    logger.warning(
        "[MCStatus] 缩放倍率 {} 会让像素字体偏离网格，已按 {} 处理。", value, fallback,
    )
    return fallback


def normalize_min_height(value: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 480


def load() -> RenderSettings:
    """从 NoneBot 插件配置读一份设置。

    读不到（比如预览脚本、单元测试里没初始化 NoneBot）就用默认值，不抛异常——
    渲染模块在 import 阶段就要用到宽度和倍率，这里失败会让整个插件加载不起来。
    """
    config = Config()
    try:
        import nonebot

        config = nonebot.get_plugin_config(Config)
    except Exception as exc:  # NoneBot 未初始化，或配置项写错类型
        logger.opt(exception=False).debug("[MCStatus] 未能读取插件配置（{}），使用默认外观。", exc)

    return RenderSettings(
        brand=config.mcs_brand,
        title=config.mcs_title,
        credit=config.mcs_credit,
        show_generated_at=bool(config.mcs_show_generated_at),
        texture=str(config.mcs_texture or PER_GROUP_TEXTURE).strip(),
        width=normalize_width(config.mcs_width),
        scale=normalize_scale(config.mcs_scale),
        min_height=normalize_min_height(config.mcs_min_height),
    )


#: 进程级设置。宽度与倍率会被 :mod:`.tokens` 在 import 时读走，改这两项必须重启。
SETTINGS: RenderSettings = load()


def current() -> RenderSettings:
    return SETTINGS


__all__ = [
    "Config", "RenderSettings", "SETTINGS", "current", "load",
    "RANDOM_TEXTURE", "NO_TEXTURE", "PER_GROUP_TEXTURE",
    "DEFAULT_CANVAS_WIDTH",
    "DEFAULT_BRAND", "DEFAULT_TITLE", "DEFAULT_CREDIT",
    "normalize_width", "normalize_scale", "normalize_min_height",
]
