#!/usr/bin/env python3
"""生成一张方形、可重复的 MC 状态图背景预览。

这里直接调用线上 :class:`Canvas` 的背景管线，因此预览包含相同的材质平铺、
釉面陶瓦 2×2 旋转图案和自适应黑色遮罩。

用法::

    python scripts/preview_mc_texture.py dirt
    python scripts/preview_mc_texture.py cyan_glazed_terracotta --size 512
    python scripts/preview_mc_texture.py stone --out /tmp/stone-background.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nonebot  # noqa: E402

nonebot.init()

from xducraft_bot.plugins.xducraft_mc_status import image_renderer as ir  # noqa: E402
from xducraft_bot.plugins.xducraft_mc_status import raster  # noqa: E402

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "preview" / "textures"


def render_texture(texture: str, output: Path, size: int) -> Path:
    resolved = ir.normalize_texture_override(texture)
    if not resolved:
        raise ValueError(f"找不到背景材质：{texture}")
    canvas = raster.Canvas(size, size)
    canvas.tile_background(resolved)
    canvas.save(str(output))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="生成方形 MC 状态图背景预览")
    parser.add_argument("texture", help="材质名称或文件名，例如 dirt / dirt.png")
    parser.add_argument("--size", type=int, default=512, help="逻辑边长，默认 512")
    parser.add_argument("--out", type=Path, help="输出 PNG；默认写入 preview/textures/")
    args = parser.parse_args()

    if args.size < 64 or args.size > 2048:
        parser.error("--size 必须在 64–2048 之间")

    resolved = ir.normalize_texture_override(args.texture)
    if not resolved:
        parser.error(f"找不到背景材质：{args.texture}")
    output = args.out or DEFAULT_OUTPUT_DIR / f"{Path(resolved).stem}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    render_texture(resolved, output, args.size)
    print(f"{resolved} -> {output} ({size_description(size=args.size)})")
    return 0


def size_description(*, size: int) -> str:
    return f"{size}×{size} 逻辑像素"


if __name__ == "__main__":
    raise SystemExit(main())
