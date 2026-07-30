#!/usr/bin/env python3
"""状态图预览：用假数据出图，不连机器人、不联网、不读群配置。

调外观的时候不该靠“改一行代码、启动机器人、在群里发一条 /mcs、盯着聊天记录看”
这套循环。这个脚本直接调 :func:`~xducraft_bot.plugins.xducraft_mc_status.
image_renderer.render_servers`——和线上出图**同一个函数**，所以看到的就是真样子。

用法::

    python scripts/preview_mc_status.py                # 出全部场景
    python scripts/preview_mc_status.py velocity       # 只出某几个
    python scripts/preview_mc_status.py --list         # 看有哪些场景
    python scripts/preview_mc_status.py --texture none # 临时换背景
    python scripts/preview_mc_status.py --min-height 0 # 试收缩到内容

图片默认写到 ``preview/``。宽度和缩放倍率是 import 期读取的，命令行改不了，
要试就在环境变量里给：``MCS_WIDTH=1200 MCS_SCALE=2 python scripts/...``。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nonebot  # noqa: E402

nonebot.init()

from xducraft_bot.plugins.xducraft_mc_status import image_renderer as ir  # noqa: E402
from xducraft_bot.plugins.xducraft_mc_status import settings as cfg  # noqa: E402
from xducraft_bot.plugins.xducraft_mc_status import tokens as t  # noqa: E402
from xducraft_bot.plugins.xducraft_mc_status.status_fetcher import (  # noqa: E402
    prepare_data_for_display, preprocess_server_data,
)

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "preview"


def server(**overrides: Any) -> Dict[str, Any]:
    """一台服务器的假数据。字段名和 status_fetcher 吐出来的一致。"""
    node: Dict[str, Any] = {
        "ip": "example.com",
        "tag": "",
        "tag_color": "",
        "online": True,
        "ping": 42,
        "version": "1.21.1",
        "players": {"online": 0, "max": 20},
        "description": None,
        "comment": "",
        "auth_mode": "",
        "children": [],
    }
    node.update(overrides)
    if not str(node.get("comment") or "").strip() and str(node.get("tag") or "").strip():
        node["comment"] = f"{node['tag']}服务器"
    return node


# ==============================================================================
# 场景
# ==============================================================================

def scenario_velocity() -> Dict[str, Any]:
    """Velocity 群组服：一个前置代理，底下挂一排子服，子服还能再挂子服。

    这是这套设计相对参考项目最大的增量——参考项目只有平铺列表，没有层级。
    """
    return {
        "footer": "群公告：赛季四已开放，进服先看 /rules。",
        "source_label": "本地协议",
        "servers": [
            server(
                ip="mc.xducraft.cn", tag="群组入口", tag_color="3181d0", ping=18,
                auth_mode="xdu", auth_detected="xdu", version="Velocity 3.4.0",
                description={"text": "§b§lXDUCraft §f群组服\n§7从这里进入任意子服"},
                players={"online": 23, "max": 200, "sample": [
                    {"name": "Steve"}, {"name": "Alex"}, {"name": "小明"}, {"name": "阿强"}]},
                children=[
                    server(
                        ip="survival.xducraft.cn", tag="生存", tag_color="2ea043", ping=22,
                        auth_mode="xdu", auth_detected="xdu",
                        description={"text": "§a生存服 §8· §f第四赛季\n§7原版生存 + 领地保护"},
                        players={"online": 12, "max": 80, "sample": [
                            {"name": "Notch"}, {"name": "建筑师老王"}]}),
                    server(
                        ip="creative.xducraft.cn", tag="创造", tag_color="f5e663", ping=25,
                        auth_mode="xdu",
                        description={"text": "§e创造服 §8· §f自由建造\n§7飞行已开放"},
                        players={"online": 6, "max": 60}),
                    server(
                        ip="minigames.xducraft.cn", tag="小游戏", tag_color="a371f7", ping=31,
                        auth_mode="mixed",
                        description={"text": "§d小游戏大厅\n§7起床战争 / 空岛战争 / 跑酷"},
                        players={"online": 5, "max": 60},
                        children=[
                            server(
                                ip="bedwars.xducraft.cn", tag="起床战争", tag_color="ff5555",
                                ping=33, auth_mode="mixed",
                                description={"text": "§cBed Wars §8· §f4v4v4v4"},
                                players={"online": 4, "max": 32}),
                            server(
                                ip="parkour.xducraft.cn", tag="跑酷", tag_color="00a8b5",
                                ping=29, auth_mode="mixed",
                                description={"text": "§bParkour §8· §f80 关"},
                                players={"online": 1, "max": 20}),
                        ]),
                    server(
                        ip="modpack.xducraft.cn", tag="模组", tag_color="dd6d1e",
                        online=False, error="connection refused", auth_mode="offline",
                        comment="整合包升级中，预计周日 20:00 恢复"),
                ]),
        ],
    }


def scenario_long_motd() -> Dict[str, Any]:
    """长 MOTD：显式换行、自动折成两行、无空格长串和像素截断。"""
    filler = "这是一段很长的服务器公告文本，用来测试两行折行与截断的表现，"
    return {
        "footer": "页脚也可以很长：" + filler * 3,
        "source_label": "自建后端",
        "servers": [
            server(
                ip="two-full-lines.example.com", tag="双行", tag_color="3181d0",
                description={"text": "§f第一行正好占满整行的内容，长度接近上限的样子\n"
                                     "§7第二行也一样长，两行都排满时应该刚好不溢出"},
                players={"online": 30, "max": 100}),
            server(
                ip="overflow.example.com", tag="超长", tag_color="da3c8f", ping=140,
                description={"text": "§c" + filler * 4},
                players={"online": 5, "max": 20}),
            server(
                ip="many-lines.example.com", tag="多行", tag_color="a371f7", ping=88,
                description={"text": "§a第一行\n§e第二行\n§c第三行会被截掉\n§9第四行也是"},
                players={"online": 2, "max": 10}),
            server(
                ip="single-word.example.com", tag="无空格", tag_color="00a8b5", ping=63,
                description={"text": "§b" + "A" * 200},
                players={"online": 1, "max": 10}),
            server(
                ip="no-motd.example.com", tag="无 MOTD", tag_color="6e7681", ping=210,
                description=None, comment="",
                players={"online": 0, "max": 10}),
        ],
    }


def scenario_rainbow() -> Dict[str, Any]:
    """彩虹名字：逐字颜色码、双色渐变、多色渐变，以及叠加各种格式码。"""
    legacy_rainbow = "".join(
        f"§{code}{char}" for code, char in zip("c6eabd5c6eabd5", "RAINBOW SERVER")
    )
    return {
        "source_label": "公共 API",
        "servers": [
            server(
                ip="legacy.example.com", tag="逐字色码", tag_color="ff5555", ping=35,
                description={"text": legacy_rainbow + "\n§7用 §c§§c§7 这类逐字颜色码拼出来的彩虹"},
                players={"online": 9, "max": 40}),
            server(
                ip="gradient2.example.com", tag="双色渐变", tag_color="55ff55", ping=47,
                description={"html": "<gradient:#55FF55:#5555FF>双色渐变 TWO STOP GRADIENT</gradient>"
                                     "<br><font color=\"gray\">参考项目支持的就是这种</font>"},
                players={"online": 14, "max": 40}),
            server(
                ip="gradient-rainbow.example.com", tag="彩虹渐变", tag_color="a371f7", ping=52,
                description={"html": "<gradient:#FF5555:#FFAA00:#FFFF55:#55FF55:#55FFFF:#5555FF:#FF55FF>"
                                     "RAINBOW 彩虹渐变横跨中英文</gradient>"
                                     "<br><font color=\"gray\">七个色标的多段渐变</font>"},
                players={"online": 21, "max": 40}),
            server(
                ip="styled.example.com", tag="格式码", tag_color="f5e663", ping=66,
                description={"text": "§a§lBOLD §c§oITALIC §9§nUNDER §e§mSTRIKE §f§kOBFUSC§r §f正常"},
                players={"online": 3, "max": 40}),
            server(
                ip="styled-gradient.example.com", tag="渐变+格式", tag_color="00a8b5", ping=95,
                description={"html": "<gradient:#FF5555:#5555FF><b>粗体渐变 BOLD GRADIENT</b></gradient>"
                                     "<br><gradient:#55FF55:#FFFF55><i>斜体渐变 ITALIC</i></gradient>"},
                players={"online": 7, "max": 40}),
        ],
    }


def scenario_auth() -> Dict[str, Any]:
    """六种登录验证方式，外加实线 / 虚线 / 配置冲突三种状态。"""
    return {
        "source_label": "本地协议",
        "servers": [
            server(ip="official.example.com", tag="正版", tag_color="2ea043",
                   auth_mode="official", auth_detected="official", ping=30,
                   description={"text": "§a已实测确认：左边条为完整实线"}),
            server(ip="mua.example.com", tag="MUA", tag_color="5865f2",
                   auth_mode="mua", ping=45,
                   description={"text": "§7仅按配置显示：左边条为不透明虚线"}),
            server(ip="xdu.example.com", tag="XDU", tag_color="1f6feb",
                   auth_mode="xdu", auth_detected="xdu", ping=60),
            server(ip="ygg.example.com", tag="外置", tag_color="00a8b5",
                   auth_mode="yggdrasil", ping=120),
            server(ip="offline.example.com", tag="离线", tag_color="db941e",
                   auth_mode="offline", auth_detected="offline", ping=220),
            server(ip="mixed.example.com", tag="混合", tag_color="a371f7",
                   auth_mode="mixed", ping=480),
            server(ip="conflict.example.com", tag="配置冲突", tag_color="ff5555",
                   auth_mode="official", auth_detected="offline", ping=75,
                   description={"text": "§6配置写的是正版，实测是离线 → 边条顶端有警示缺口"}),
            server(ip="none.example.com", tag="未配置", tag_color="6e7681", ping=90,
                   description={"text": "§8没有验证方式配置 → 边条保持中性白"}),
        ],
    }


def scenario_latency() -> Dict[str, Any]:
    """五个延迟档位，看信号条与状态色是否连续。"""
    return {
        "source_label": "本地协议",
        "servers": [
            server(ip="excellent.example.com", tag="极佳 <100", tag_color="55ff55", ping=23),
            server(ip="good.example.com", tag="良好 <200", tag_color="ffff55", ping=150),
            server(ip="fair.example.com", tag="一般 <400", tag_color="ffaa00", ping=310),
            server(ip="poor.example.com", tag="较差 >=400", tag_color="ff5555", ping=880),
            server(ip="dead.example.com", tag="离线", tag_color="6e7681",
                   online=False, error="timeout", comment="连不上"),
        ],
    }


def scenario_empty() -> Dict[str, Any]:
    """一台服务器都没有的空态。"""
    return {"servers": []}


def scenario_minimal() -> Dict[str, Any]:
    """单台服务器。用来看 MCS_MIN_HEIGHT 的效果最直观。"""
    return {
        "source_label": "本地协议",
        "servers": [server(ip="only.example.com", tag="唯一一台", tag_color="3181d0",
                           description={"text": "§f就这一台"})],
    }


SCENARIOS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "velocity": scenario_velocity,
    "long-motd": scenario_long_motd,
    "rainbow": scenario_rainbow,
    "auth": scenario_auth,
    "latency": scenario_latency,
    "minimal": scenario_minimal,
    "empty": scenario_empty,
}


# ==============================================================================
# 出图
# ==============================================================================

def render(name: str, output_dir: Path, settings: cfg.RenderSettings) -> Path:
    scenario = SCENARIOS[name]()
    servers = preprocess_server_data(scenario.get("servers", []))
    display = prepare_data_for_display(servers, True)

    destination = output_dir / f"{name}.png"
    ir.render_servers(
        display, str(destination),
        footer_text=scenario.get("footer", ""),
        source_label=scenario.get("source_label", ""),
        group_default_auth=scenario.get("group_default_auth", ""),
        # 用场景名当“群号”：按群号挑材质的默认策略下，每个场景固定一张背景，
        # 改代码前后对比时背景不会乱跳。
        group_id=abs(hash(name)) % 10**8,
        settings=settings,
    )
    return destination


def build_settings(args: argparse.Namespace) -> cfg.RenderSettings:
    settings = cfg.current()
    changes: Dict[str, Any] = {}
    if args.texture is not None:
        changes["texture"] = args.texture
    if args.brand is not None:
        changes["brand"] = args.brand
    if args.title is not None:
        changes["title"] = args.title
    if args.credit is not None:
        changes["credit"] = args.credit
    if args.no_generated_at:
        changes["show_generated_at"] = False
    if args.min_height is not None:
        changes["min_height"] = cfg.normalize_min_height(args.min_height)
    return settings.evolve(**changes) if changes else settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="用假数据预览 MC 状态图",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="场景：" + "、".join(SCENARIOS),
    )
    parser.add_argument("scenarios", nargs="*", help="要出的场景，留空表示全部")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--list", action="store_true", help="列出所有场景后退出")
    parser.add_argument("--texture", help="背景材质：文件名 / random / none")
    parser.add_argument("--brand", help="顶栏品牌行")
    parser.add_argument("--title", help="图片主标题")
    parser.add_argument("--credit", help="底栏署名")
    parser.add_argument("--no-generated-at", action="store_true", help="不显示生成时间")
    parser.add_argument("--min-height", type=int, help="最小逻辑高度，0 表示收缩到内容")
    args = parser.parse_args()

    if args.list:
        for name, factory in SCENARIOS.items():
            summary = (factory.__doc__ or "").strip().splitlines()[0]
            print(f"{name:12s} {summary}")
        return 0

    unknown = [name for name in args.scenarios if name not in SCENARIOS]
    if unknown:
        parser.error(f"未知场景：{', '.join(unknown)}（可用：{', '.join(SCENARIOS)}）")

    settings = build_settings(args)
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"画布 {t.CANVAS_WIDTH}×{t.SCALE} 倍，最小高度 "
          f"{settings.min_height or '收缩到内容'}，材质 {settings.texture or '按群号'}")
    for name in args.scenarios or list(SCENARIOS):
        path = render(name, args.out, settings)
        size = os.path.getsize(path)
        print(f"  {name:12s} -> {path}  ({size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
