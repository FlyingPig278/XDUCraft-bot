"""状态图渲染的不变量。

这里只测**会静默失败**的东西。像素字体的字号偏离网格、某个排版角色缺了中日韩
搭档字体，运行时都不会报任何错——图照出，只是糊了或者变成一排豆腐块，除非有人
恰好盯着看，否则可以坏上好几个月。
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from xducraft_bot.plugins.xducraft_mc_status import fonts, raster, tokens as t
from xducraft_bot.plugins.xducraft_mc_status import drawing_utils as du
from xducraft_bot.plugins.xducraft_mc_status import image_renderer as ir
from xducraft_bot.plugins.xducraft_mc_status import settings as cfg
from xducraft_bot.plugins.xducraft_mc_status import split_query_options

ROLES = [
    fonts.EYEBROW, fonts.TITLE, fonts.SUBTITLE, fonts.CHIP, fonts.MOTD,
    fonts.ADDRESS, fonts.MICRO, fonts.DATA, fonts.VERSION, fonts.LABEL,
]

CJK = "服务器状态在线离线延迟版本玩家验证登录混合正版第三方外置"


def _gray_levels(font, text: str) -> int:
    """栅格里的灰阶数量。2 = 纯像素，30+ = 字号没落在网格上被插值糊了。"""
    size = int(font.size)
    canvas = Image.new("L", (size * len(text) + 40, size * 3), 0)
    ImageDraw.Draw(canvas).text((4, 4), text, font=font, fill=255)
    return len(np.unique(np.array(canvas)))


@pytest.mark.parametrize("role", ROLES, ids=lambda role: role.name)
def test_role_sizes_land_on_the_pixel_grid(role):
    """每个角色的字号都必须落在它所用字体的像素网格上。

    偏离网格不会报错，只会让本该非黑即白的像素边缘变成灰糊。旧实现的
    17 / 21 / 29px 就全部偏了。
    """
    for face in role.faces:
        step = fonts._GRID.get(_face_name(face))
        if step is None:
            continue
        assert role.size % step == 0, (
            f"角色 {role.name} 的字号 {role.size}px 不是 {_face_name(face)} 的网格步长 "
            f"{step} 的倍数，字形会被插值糊掉"
        )


def _face_name(face):
    import os

    return os.path.basename(getattr(face, "path", ""))


def test_pixel_faces_render_crisply_at_their_role_size():
    """网格约束真的能换来纯像素栅格——不是纸面规则。"""
    body = fonts.load_face(fonts.FACE_BODY, fonts.MOTD.size)
    assert _gray_levels(body, "ABC 123") == 2

@pytest.mark.parametrize("role", ROLES, ids=lambda role: role.name)
def test_no_role_renders_cjk_as_tofu(role):
    """任何角色都不能把中日韩字符画成 .notdef 豆腐块。

    Minecraft Ten / Five / Monocraft 都只有一两百个字形，全是拉丁字符。
    Pillow 没有字体回退，谁把某个角色的中日韩搭档字体删掉，标题就会变成一排方框。
    """
    for character in CJK:
        face = role.face_for(character)
        assert fonts.covers(face, character), (
            f"角色 {role.name} 画不出 {character!r}，会出现豆腐块"
        )


def test_latin1_punctuation_never_reaches_the_font_raw():
    """Minecraft AE 把 Latin-1 整块当成原版重音字符页，必须先改写。"""
    assert fonts.remap("A·B»C«D×E") == "A\u2027B>C<Dx E".replace(" ", "")
    assert "\u00b7" not in fonts.remap("中·文")
    # 改写要在度量与绘制的共同入口上生效，两边才对得齐。
    runs = fonts.SUBTITLE.split("A·B")
    assert "\u00b7" not in "".join(part for part, _ in runs)


def test_measured_width_matches_drawn_width():
    """度量和绘制必须同一把尺子。

    字体是按物理字号加载的，度量天然是物理像素；如果哪里又乘了一遍 SCALE，
    右对齐的文本就会飞到画布外——而左对齐的一切看起来都正常，很难发现。
    """
    canvas = raster.Canvas(200, 40)
    anchor_x = 180
    canvas.text("42 ms 在线", (anchor_x, 20), fonts.DATA, (255, 255, 255, 255), "rm")

    ink = np.array(canvas.image.convert("L")) > 24
    rightmost = int(np.max(np.where(ink.any(axis=0))[0]))
    assert abs(rightmost - t.px(anchor_x)) <= t.px(2), (
        f"右对齐文本落在 {rightmost}px，锚点在 {t.px(anchor_x)}px"
    )


def test_motd_preserves_two_explicit_lines():
    segments = du.parse_minecraft_formatting(
        "§b第一行\n§7第二行", (255, 255, 255, 255),
    )
    lines = du.wrap_segments(segments, fonts.MOTD, 600 * t.SCALE, t.MOTD_LINES)

    assert len(lines) == 2
    assert "".join(segment.text for segment in lines[0]) == "第一行"
    assert "".join(segment.text for segment in lines[1]) == "第二行"


def test_long_motd_wraps_and_truncates_at_two_rows():
    segments = du.parse_minecraft_formatting(
        "§b第一行很长" + "内容" * 80, (255, 255, 255, 255),
    )
    width = 300 * t.SCALE
    lines = du.wrap_segments(segments, fonts.MOTD, width, t.MOTD_LINES)
    assert len(lines) == 2
    assert all(du.measure_segments(line, fonts.MOTD) <= width + 1 for line in lines)
    assert lines[-1][-1].text == "…"


def test_format_codes_survive_parsing():
    """§k–§o 必须进到样式位，而不是被消费掉后丢弃。"""
    segments = du.parse_minecraft_formatting("§lB§oI§nU§mS§kK", (255, 255, 255, 255))
    flags = {
        "bold": any(s.bold for s in segments),
        "italic": any(s.italic for s in segments),
        "underline": any(s.underline for s in segments),
        "strikethrough": any(s.strikethrough for s in segments),
        "obfuscated": any(s.obfuscated for s in segments),
    }
    assert all(flags.values()), flags
    # 颜色码按原版规则清空所有格式位。
    assert not any(s.bold for s in du.parse_minecraft_formatting("§lB§aA", (255,) * 4)[1:])


def test_state_colors_come_from_the_minecraft_palette():
    """状态色必须是原版聊天调色板里的颜色，不能另造。"""
    from xducraft_bot.plugins.xducraft_mc_status.constants import MINECRAFT_COLOR_CODES

    palette = set(MINECRAFT_COLOR_CODES.values())
    for color in raster.TIER_COLORS.values():
        assert color in palette


def test_latency_tiers_are_monotonic():
    """延迟越高，档位越差，亮起的信号格只减不增。"""
    tiers = [raster.ping_tier(ping, True) for ping in (10, 150, 300, 900)]
    bars = [raster.TIER_BARS[tier] for tier in tiers]
    assert bars == sorted(bars, reverse=True)
    assert raster.TIER_BARS[raster.ping_tier(None, False)] == 0


def _offline_rail_calls():
    """跑一遍离线卡片的右栏，把画了什么文字、画在哪记下来。"""
    node = {"online": False, "error": "timeout", "version": "1.21.1",
            "players": {"online": 9, "max": 20}, "children": []}
    card = ir.CardLayout(node=node, level=0, top=0)

    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT + 20)
    drawn = []
    canvas.text = lambda text, xy, *a, **k: (  # type: ignore[assignment]
        drawn.append((text, xy)) or 0.0
    )
    canvas.segments = lambda segs, xy, *a, **k: (  # type: ignore[assignment]
        drawn.append(("".join(s.text for s in segs), xy)) or 0.0
    )
    ir._draw_rail(canvas, card)
    return card, drawn


def test_offline_card_hides_stale_version_and_player_count():
    """离线卡片不能显示上次查询缓存下来的版本号和人数。

    摆在“离线”旁边会让人以为服务器还在报活。
    """
    _, drawn = _offline_rail_calls()
    texts = [text for text, _ in drawn]

    assert "离线" in texts
    assert "1.21.1" not in texts
    assert "9/20" not in texts
    # “连接失败”和“离线”说的是同一件事，只留一个。
    assert "连接失败" not in texts


def test_offline_label_stays_inside_the_latency_slot():
    """“离线”只顶掉延迟数字那一格，不能压到信号条上。

    信号条永远画在右栏最右边；离线标签右对齐，锚点必须落在信号条左侧。
    早先写 OFFLINE 时七个字母正好会伸进信号条里。
    """
    card, drawn = _offline_rail_calls()
    anchors = {text: xy for text, xy in drawn}
    assert "离线" in anchors

    bars_width = t.SIGNAL_BARS * ir.BAR_WIDTH + (t.SIGNAL_BARS - 1) * ir.BAR_GAP
    signal_left = card.rail_right - bars_width
    assert anchors["离线"][0] <= signal_left, "离线标签的右边界伸进了信号条的位置"


def test_auth_colors_and_state_colors_never_share_a_slot():
    """色相分区：状态色只在右栏，验证方式色只在左边条。

    两边撞色的话，绿色既可能是“延迟低”又可能是“正版登录”，图就没法读了。
    """
    from xducraft_bot.plugins.xducraft_mc_status import auth_mode as auth

    state = {tuple(color) for color in raster.TIER_COLORS.values()}
    stripe = {
        tuple(du.as_rgba(auth.style_for(mode).color)) for mode in auth.CONFIGURABLE_MODES
    }
    assert not (state & stripe)


# ==============================================================================
# 渲染选项
# ==============================================================================

def test_scale_only_accepts_grid_safe_values():
    """倍率直接决定物理字号，奇数倍率会让一部分角色偏离像素网格。"""
    assert cfg.normalize_scale(2) == 2
    assert cfg.normalize_scale(4) == 4
    for bad in (0, 1, 3, 5, -2, "x", None):
        assert cfg.normalize_scale(bad) in (2, 4)

    # 真正要守住的是这条：允许的倍率下，每个角色都还落在网格上。
    for scale in (2, 4):
        for logical in (
            t.TYPE_EYEBROW, t.TYPE_TITLE, t.TYPE_SUBTITLE, t.TYPE_CHIP,
            t.TYPE_MOTD, t.TYPE_ADDRESS, t.TYPE_MICRO, t.TYPE_LABEL, t.TYPE_DATA,
        ):
            assert (logical * scale) % 8 == 0, (logical, scale)


def test_width_is_clamped_to_a_sane_range():
    assert cfg.normalize_width(100) == 640
    assert cfg.normalize_width(99999) == 1600
    assert cfg.normalize_width(854) == 854


def test_min_height_zero_collapses_to_content():
    """MCS_MIN_HEIGHT=0 要真的贴着内容收边，而不是继续撑到 480。"""
    tall = ir.calculate_image_height(120, 90, "", [], band=True, min_height=480)
    tight = ir.calculate_image_height(120, 90, "", [], band=True, min_height=0)
    assert tall == 480
    assert tight < tall
    assert tight >= 120 + 90 + ir.band_height("")


def test_hiding_the_band_removes_its_dynamic_height():
    with_band = ir.calculate_image_height(120, 400, "公告", [], band=True, min_height=0)
    without = ir.calculate_image_height(120, 400, "公告", [], band=False, min_height=0)
    assert with_band - without == ir.band_height("公告")


def test_blank_header_rows_do_not_reserve_space():
    """品牌行 / 标题留空时那一行不占高度，列表整体上移。"""
    full = ir.header_metrics(cfg.RenderSettings())
    no_brand = ir.header_metrics(cfg.RenderSettings(brand=""))
    bare = ir.header_metrics(cfg.RenderSettings(brand="", title=""))

    assert full.eyebrow_y is not None and full.title_y is not None
    assert no_brand.eyebrow_y is None and no_brand.title_y is not None
    assert bare.eyebrow_y is None and bare.title_y is None
    assert bare.list_top < no_brand.list_top < full.list_top


def test_header_uses_spacing_without_a_divider_line():
    settings = cfg.RenderSettings()
    canvas = raster.Canvas(t.CANVAS_WIDTH, 160)
    canvas.hline = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("divider drawn"))  # type: ignore[assignment]
    ir._draw_header(
        canvas,
        {"online": 1, "total": 1, "players_online": 2, "players_max": 20},
        "protocol",
        ir.header_metrics(settings),
        settings,
    )


def test_band_disappears_only_when_nothing_is_left_in_it():
    assert ir.band_is_visible(cfg.RenderSettings())
    assert ir.band_is_visible(cfg.RenderSettings(credit="", show_generated_at=True))
    assert ir.band_is_visible(cfg.RenderSettings(credit="x", show_generated_at=False))
    assert not ir.band_is_visible(cfg.RenderSettings(credit="", show_generated_at=False))


def test_footer_announcement_uses_opaque_ink():
    settings = cfg.RenderSettings(credit="", show_generated_at=False)
    canvas = raster.Canvas(t.CANVAS_WIDTH, 100)
    calls = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        calls.append((text, fill)) or 0.0
    )
    ir._draw_band(canvas, 100, "服务器公告", settings)
    assert calls == [("服务器公告", t.INK)]


def test_texture_selection_honours_every_mode():
    available = raster.list_textures()
    assert available, "预览与出图都依赖 resources/textures 里的方块材质"

    assert ir.resolve_texture(cfg.RenderSettings(texture=cfg.NO_TEXTURE), 1) == ""
    assert ir.resolve_texture(cfg.RenderSettings(texture=cfg.RANDOM_TEXTURE), 1) in available
    assert ir.resolve_texture(cfg.RenderSettings(texture=available[0]), 1) == available[0]
    # 配置写了一张不存在的材质，退回兜底而不是变纯黑。
    assert ir.resolve_texture(cfg.RenderSettings(texture="nope.png"), 1) in available


def test_query_texture_option_accepts_name_with_or_without_extension():
    available = raster.list_textures()
    assert ir.normalize_texture_override("dirt", available) == "dirt.png"
    assert ir.normalize_texture_override("DIRT.PNG", available) == "dirt.png"
    assert ir.normalize_texture_override("../dirt", available) == ""
    assert ir.normalize_texture_override("missing", available) == ""


def test_request_texture_overrides_fixed_random_and_none_config():
    assert ir.resolve_texture(cfg.RenderSettings(texture="stone.png"), 1, "dirt") == "dirt.png"
    assert ir.resolve_texture(cfg.RenderSettings(texture=cfg.RANDOM_TEXTURE), 1, "dirt") == "dirt.png"
    assert ir.resolve_texture(cfg.RenderSettings(texture=cfg.NO_TEXTURE), 1, "dirt") == "dirt.png"


def test_missing_request_texture_falls_back_to_fixed_config():
    settings = cfg.RenderSettings(texture="stone.png")
    assert ir.resolve_texture(settings, 1, "does-not-exist") == "stone.png"


def test_query_texture_argument_can_appear_before_or_after_target():
    assert split_query_options(["all", "texture=dirt"]) == (["all"], "dirt")
    assert split_query_options(["texture=dirt", "mc.example.com"]) == (["mc.example.com"], "dirt")
    assert split_query_options(["texture=stone", "texture=dirt"]) == ([], "dirt")


def test_per_group_texture_is_stable_across_runs():
    """按群号挑材质必须可复现，否则每次重启全群的图都换个皮肤。"""
    settings = cfg.RenderSettings(texture=cfg.PER_GROUP_TEXTURE)
    first = ir.resolve_texture(settings, 123456789)
    assert first == ir.resolve_texture(settings, 123456789)
    others = {ir.resolve_texture(settings, group) for group in range(20)}
    assert len(others) > 1, "不同群应该拿到不同背景"


# ==============================================================================
# 渐变与粗体
# ==============================================================================

def test_gradient_accepts_more_than_two_stops():
    """彩虹名字要靠多色标；只支持双色标做不出彩虹。"""
    segments = du.parse_minecraft_formatting(
        "<gradient:#FF5555:#FFFF55:#55FF55:#5555FF>RAINBOW</gradient>",
        (255,) * 4, is_html=True,
    )
    assert segments and segments[0].gradient is not None
    assert len(segments[0].gradient) == 4


def _red_profile(canvas, bins: int = 6):
    """把画布上的字按 x 分箱，量每一箱的平均红色分量。

    只取“实心”像素（三通道和 > 200）：纯色渐变在满覆盖处通道和约等于 255，
    边缘反锯齿像素会低很多，混进来会把信号搅成噪声。
    """
    pixels = np.array(canvas.image).astype(float)
    core = pixels.sum(axis=2) > 200
    rows, columns = np.nonzero(core)
    assert columns.size, "画布上没有实心像素"

    reds = pixels[rows, columns, 0]
    edges = np.linspace(columns.min(), columns.max() + 1, bins + 1)
    profile = []
    for low, high in zip(edges[:-1], edges[1:]):
        selected = (columns >= low) & (columns < high)
        if selected.any():
            profile.append(float(reds[selected].mean()))
    return profile


def test_gradient_sweeps_once_across_a_mixed_script_span():
    """渐变要横跨整个区间，不能每换一次字体就跳回起点。

    断裂发生在 :meth:`FontSet.split` 切出来的 **run** 边界上，所以必须挑一个
    真会分段的角色：MOTD 只用 Minecraft AE 一款字体，中英文都由它画，永远不分段，
    拿它测等于什么都没测。TITLE 是 Minecraft Ten + Vonwaon，中英交界处一定断开。

    判据是像素：红→蓝的渐变从左到右扫过去，红色分量只能一路降。实测正常时
    profile 是 [232, 189, 150, 106, 62, 21]；每个 run 各扫一遍的话会变成
    [207, 115, 55, 199, 117, 39]——中英交界处直接跳回去 144。
    """
    segments = du.parse_minecraft_formatting(
        "<gradient:#FF0000:#0000FF>AAAAAA中文中文</gradient>", (255,) * 4, is_html=True,
    )
    assert len(fonts.TITLE.split(segments[0].text)) > 1, "这段文本必须真的跨字体，测试才有意义"

    canvas = raster.Canvas(500, 80)
    canvas.segments(segments, (10, 40), fonts.TITLE, "lm")

    profile = _red_profile(canvas)
    rises = [after - before for before, after in zip(profile, profile[1:])]
    assert max(rises) < 0, f"红色分量中途回升，渐变在字体边界处重新开始了：{profile}"


def test_gradient_spans_every_segment_it_wraps():
    """一个 ``<gradient>`` 里嵌了别的格式标签时会分出多个 segment，扫描线仍要共用。"""
    segments = du.parse_minecraft_formatting(
        "<gradient:#FF0000:#0000FF>plain<b>bold</b>tail</gradient>", (255,) * 4, is_html=True,
    )
    assert len(segments) > 1, "嵌套标签必须切出多个 segment，测试才有意义"
    assert all(segment.gradient is not None for segment in segments)

    widths = [du.measure_segments([segment], fonts.MOTD) for segment in segments]
    spans = raster._gradient_spans(segments, widths, 0.0)
    assert len(set(spans)) == 1, "同一个 <gradient> 区间必须共享一条扫描线"
    assert spans[0][1] == pytest.approx(sum(widths))


def test_bold_is_lighter_on_full_width_glyphs():
    """全角字形画在 16px 网格上，粗体偏移必须是半角的一半。

    照半角的偏移重描，32px 的中文会糊成一团。
    """
    narrow = du.bold_offset_for(fonts.MOTD, "A")
    wide = du.bold_offset_for(fonts.MOTD, "服")
    assert du.is_full_width(fonts.MOTD, "服")
    assert not du.is_full_width(fonts.MOTD, "A")
    assert wide * 2 <= narrow <= wide * 2 + 1


def test_bold_measurement_matches_what_gets_drawn():
    """度量与绘制必须用同一套逐字偏移，否则右对齐的粗体会跑偏。"""
    text = "BOLD 粗体混排"
    segment = du.Segment(text, (255,) * 4, bold=True)
    expected = fonts.MOTD.length(text) + sum(
        du.bold_offset_for(fonts.MOTD, ch) for ch in fonts.remap(text)
    )
    assert du.measure_segments([segment], fonts.MOTD) == pytest.approx(expected)

    canvas = raster.Canvas(300, 50)
    anchor_x = 280
    canvas.segments([segment], (anchor_x, 25), fonts.MOTD, "rm")
    ink = np.array(canvas.image.convert("L")) > 24
    rightmost = int(np.max(np.where(ink.any(axis=0))[0]))
    assert abs(rightmost - t.px(anchor_x)) <= t.px(2)


# ==============================================================================
# 对比度与卡片几何
# ==============================================================================

@pytest.mark.parametrize(
    "background, expected",
    [
        ((0x55, 0xFF, 0x55, 255), "dark"),   # 亮绿：旧的亮度阈值算成 184.8，差 1.2 判成白字
        ((0xFF, 0xFF, 0x55, 255), "dark"),   # 亮黄
        ((0x55, 0xFF, 0xFF, 255), "dark"),   # 亮青
        ((0xFF, 0xAA, 0x00, 255), "dark"),   # 橙
        ((0xDB, 0x94, 0x1E, 255), "dark"),   # 琥珀
        ((0xFF, 0xFF, 0xFF, 255), "dark"),   # 纯白
        ((0x22, 0x22, 0x22, 255), "light"),  # 近黑
        ((0x1F, 0x6F, 0xEB, 255), "light"),  # XDU 蓝
        ((0x58, 0x65, 0xF2, 255), "light"),  # MUA 靛
        ((0x31, 0x81, 0xD0, 255), "dark"),   # 中间调蓝：黑 5.18 / 白 4.05，白字连 AA 都不到
        ((0xB4, 0x5A, 0xB4, 255), "dark"),   # 中间调紫：黑 5.06 / 白 4.15，同上
    ],
)
def test_ink_follows_wcag_contrast(background, expected):
    """浅底自动换黑字。亮绿必须和亮黄一样拿黑字。"""
    ink = raster.ink_for_background(background)
    assert ink == (t.INK_DARK if expected == "dark" else t.INK)


def test_lime_and_yellow_agree_now():
    """同样刺眼的亮绿和亮黄不能一个白字一个黑字——这正是旧实现的毛病。"""
    lime = raster.ink_for_background((0x55, 0xFF, 0x55, 255))
    yellow = raster.ink_for_background((0xFF, 0xFF, 0x55, 255))
    assert lime == yellow == t.INK_DARK


def test_relative_luminance_matches_the_wcag_reference_values():
    """对着 WCAG 定义的几个已知值校准，别把系数写反。"""
    assert du.relative_luminance((0, 0, 0, 255)) == pytest.approx(0.0)
    assert du.relative_luminance((255, 255, 255, 255)) == pytest.approx(1.0)
    assert du.contrast_ratio((0, 0, 0, 255), (255, 255, 255, 255)) == pytest.approx(21.0)
    # 绿色的权重最高，蓝色最低——旧的 0.299/0.587/0.114 把绿压得太低。
    green = du.relative_luminance((0, 255, 0, 255))
    blue = du.relative_luminance((0, 0, 255, 255))
    assert green > 0.7 and blue < 0.1


def test_chosen_ink_is_never_the_worse_of_the_two():
    """任何背景下都不能选到对比度更低的那一边。

    这条不变量直接否掉了中途试过的“容差”写法：那版为了让中间色保持白字，
    在 (180, 90, 180) 上选了 4.15 的白字而不是 5.06 的黑字，连 AA 都不到。
    """
    for background in [(r, g, b, 255) for r in (0, 90, 180, 255)
                       for g in (0, 90, 180, 255) for b in (0, 90, 180, 255)]:
        ink = raster.ink_for_background(background)
        other = t.INK if ink == t.INK_DARK else t.INK_DARK
        assert du.contrast_ratio(ink, background) >= du.contrast_ratio(other, background), (
            f"{background} 选了对比度更低的一边"
        )


def test_auth_stripe_sits_outside_the_bordered_box():
    """色条挂在方框外面，不占卡片的内边距。"""
    card = ir.CardLayout(node={"children": []}, level=0, top=0)

    assert card.box_left == card.left + t.AUTH_STRIPE_WIDTH
    assert card.icon_left == card.box_left + t.CARD_PAD
    assert card.icon_left - card.box_left == t.CARD_PAD


def test_latency_is_one_compact_right_aligned_text_run():
    node = {
        "online": True, "ping": 42, "version": "1.21.1",
        "players": {"online": 3, "max": 20}, "children": [],
    }
    card = ir.CardLayout(node=node, level=0, top=0)
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    drawn = []
    rich_segments = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        drawn.append((text, xy, font, anchor)) or canvas.measure(text, font)
    )
    def capture_segments(segs, xy, font, anchor="lm", **kwargs):
        rich_segments.extend(segs)
        drawn.append(("".join(s.text for s in segs), xy, font, anchor))
        return 0.0
    canvas.segments = capture_segments  # type: ignore[assignment]
    ir._draw_rail(canvas, card)
    calls = {text: (xy, font, anchor) for text, xy, font, anchor in drawn}

    assert calls["42ms"][2] == "rm"
    assert "42" not in calls and "ms" not in calls
    assert calls["1.21.1"][1] is fonts.VERSION
    assert fonts.VERSION.size == fonts.DATA.size
    assert all(segment.color == t.INK_GHOST for segment in rich_segments)


def test_compact_card_and_icon_share_edge_padding():
    assert t.CARD_HEIGHT == 80
    assert t.ICON_SIZE == 64
    assert t.ICON_SIZE == t.CARD_HEIGHT - 2 * t.CARD_PAD


def test_status_stack_fits_above_address_row():
    first, second, third = ir.RAIL_ROW_Y
    assert second - first == third - second
    assert third < ir.ROW_META_Y




def test_version_is_visibly_translucent_after_rasterization():
    translucent = raster.Canvas(120, 40)
    opaque = raster.Canvas(120, 40)
    translucent.text("1.21.1", (8, 20), fonts.VERSION, t.INK_GHOST)
    opaque.text("1.21.1", (8, 20), fonts.VERSION, t.INK)
    assert np.array(translucent.image).max() < 200
    assert np.array(opaque.image).max() == 255


def test_version_and_counter_have_matching_optical_height():
    counter_box = fonts.DATA.primary.getbbox("30/100")
    version_box = fonts.VERSION.primary.getbbox("1.21.1")
    counter_height = counter_box[3] - counter_box[1]
    version_height = version_box[3] - version_box[1]
    assert abs(version_height - counter_height) <= 2


def test_motd_is_larger_than_status_data():
    assert fonts.MOTD.size > fonts.DATA.size


def test_offline_icon_is_not_dimmed():
    card = ir.CardLayout(node={"children": []}, level=0, top=0)
    icon = Image.new("RGBA", (t.px(t.ICON_SIZE), t.px(t.ICON_SIZE)), (200, 40, 20, 255))
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    ir._draw_icon(canvas, icon, card, online=False)
    pixel = canvas.image.getpixel((t.px(card.icon_left + 2), t.px(card.icon_top + 2)))
    assert pixel == (200, 40, 20)


def test_server_icon_draws_without_an_inner_border():
    card = ir.CardLayout(node={"children": []}, level=0, top=0)
    icon = Image.new("RGBA", (t.px(t.ICON_SIZE), t.px(t.ICON_SIZE)), (200, 40, 20, 255))
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    canvas.rect = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("icon border drawn"))  # type: ignore[assignment]
    ir._draw_icon(canvas, icon, card, online=True)


def test_tagged_and_tagless_cards_always_use_fixed_gap():
    nodes = [
        {"tag": "A", "children": []},
        {"tag": "", "children": []},
        {"tag": "B", "children": []},
    ]
    cards, _ = ir.build_layout(nodes, 100)

    assert [card.top for card in cards] == [
        100,
        100 + t.CARD_HEIGHT + t.CARD_GAP,
        100 + 2 * (t.CARD_HEIGHT + t.CARD_GAP),
    ]
    assert t.CARD_GAP > 4


def test_tag_overlay_shares_card_bottom_left_anchor():
    node = {"tag": "生存", "tag_color": "3181D0", "children": []}
    card = ir.CardLayout(node=node, level=0, top=100)
    canvas = raster.Canvas(t.CANVAS_WIDTH, 200)
    texts = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        texts.append((text, xy, anchor)) or canvas.measure(text, font)
    )
    box = ir._draw_tag_overlay(canvas, card)

    assert box is not None
    assert box[0] == card.box_left
    assert box[1] == card.bottom - t.TAG_CHIP_HEIGHT
    assert box[3] == card.bottom
    assert texts[0][2] == "lm"


def test_long_tag_pushes_address_right_of_tag_edge():
    node = {
        "tag": "very-long-tag " * 20,
        "tag_color": "3181D0",
        "players": {"sample": [{"name": "Steve"}, {"name": "Alex"}]},
        "children": [],
    }
    card = ir.CardLayout(node=node, level=0, top=0)
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    text_calls = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        text_calls.append((text, xy)) or canvas.measure(text, font)
    )
    ir._draw_meta_row(canvas, card, "an-extremely-long-address-" * 20, resolved=None)
    layout = ir._tag_layout(canvas, card)
    assert layout is not None
    expected_left = max(card.body_left, card.box_left + layout[2] + t.TAG_ADDRESS_GAP)
    assert expected_left > card.body_left
    assert text_calls[0][1][0] == expected_left

    assert expected_left - (card.box_left + layout[2]) == t.TAG_ADDRESS_GAP
    assert len(text_calls) == 1, "地址优先时玩家列表必须主动让位"


def test_short_player_list_is_shown_in_full_with_green_dot():
    node = {
        "players": {"sample": [{"name": "Steve"}, {"name": "Alex"}]},
        "children": [],
    }
    card = ir.CardLayout(node=node, level=0, top=0)
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    texts = []
    dots = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        texts.append(text) or canvas.measure(text, font)
    )
    canvas.rect = lambda box, **kwargs: dots.append((box, kwargs.get("fill")))  # type: ignore[assignment]
    ir._draw_meta_row(canvas, card, "short.example.com", resolved=None)
    assert texts[-1] == "Steve · Alex"
    assert dots[-1][1] == t.STATE_EXCELLENT


def test_long_player_list_truncates_to_remaining_width():
    names = [{"name": f"VeryLongPlayerName{index}"} for index in range(30)]
    card = ir.CardLayout(node={"players": {"sample": names}, "children": []}, level=0, top=0)
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    texts = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        texts.append(text) or canvas.measure(text, font)
    )
    ir._draw_meta_row(canvas, card, "x.io", resolved=None)
    assert texts[-1].endswith("…")

def test_header_statuses_are_plain_text_with_green_dots():
    canvas = raster.Canvas(t.CANVAS_WIDTH, 80)
    boxes = []
    texts = []
    canvas.rect = lambda box, **kwargs: boxes.append((box, kwargs.get("fill"), kwargs.get("outline")))  # type: ignore[assignment]
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: (  # type: ignore[assignment]
        texts.append(text) or canvas.measure(text, font)
    )
    ir._draw_header_statuses(
        canvas, {"online": 3, "total": 5, "players_online": 12}, 800, 30,
    )
    assert texts == ["3/5服务器在线", "12人在线"]
    dots = [box for box, fill, outline in boxes if fill == t.STATE_EXCELLENT and outline is None]
    assert len(dots) == 2


def test_header_status_dot_turns_red_for_each_zero_counter():
    canvas = raster.Canvas(t.CANVAS_WIDTH, 80)
    fills = []
    canvas.rect = lambda box, **kwargs: fills.append(kwargs.get("fill"))  # type: ignore[assignment]
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: canvas.measure(text, font)  # type: ignore[assignment]
    ir._draw_header_statuses(
        canvas, {"online": 0, "total": 5, "players_online": 0}, 800, 30,
    )
    assert fills == [t.STATE_POOR, t.STATE_POOR]


def test_signal_bars_extend_to_nine_pixels_but_stay_below_text_size():
    canvas = raster.Canvas(100, 40)
    boxes = []
    canvas.rect = lambda box, **kwargs: boxes.append(box)  # type: ignore[assignment]
    ir._draw_signal(canvas, 90, 20, "excellent")
    heights = [bottom - top for _, top, _, bottom in boxes]
    assert max(heights) == 9
    assert max(heights) < t.TYPE_DATA


def test_auth_method_is_underlined_colored_text_not_a_badge():
    from types import SimpleNamespace
    from xducraft_bot.plugins.xducraft_mc_status import auth_mode as auth

    resolved = SimpleNamespace(mode=auth.MODE_XDU, style=auth.style_for(auth.MODE_XDU))
    card = ir.CardLayout(node={"children": []}, level=0, top=0)
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    segments = []
    canvas.text = lambda text, xy, font, fill, anchor="lm", **kwargs: canvas.measure(text, font)  # type: ignore[assignment]
    canvas.segments = lambda items, *args, **kwargs: segments.extend(items) or 0.0  # type: ignore[assignment]
    ir._draw_meta_row(canvas, card, "mc.example.com", resolved)
    assert len(segments) == 1
    assert segments[0].text == resolved.style.short_label
    assert segments[0].underline
    assert segments[0].color == ir._auth_color(resolved)


def test_config_only_auth_stripe_is_opaque_and_dashed():
    from types import SimpleNamespace
    from xducraft_bot.plugins.xducraft_mc_status import auth_mode as auth

    card = ir.CardLayout(node={"children": []}, level=0, top=0)
    resolved = SimpleNamespace(
        mode=auth.MODE_MUA,
        confirmed=False,
        conflict=False,
        style=auth.style_for(auth.MODE_MUA),
    )
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    boxes = []
    canvas.rect = lambda box, **kwargs: boxes.append((box, kwargs.get("fill")))  # type: ignore[assignment]
    ir._draw_auth_stripe(canvas, card, resolved)

    assert len(boxes) > 1
    assert all(fill[3] == 255 for _, fill in boxes)
    assert all(bottom - top <= t.AUTH_DASH for (_, top, _, bottom), _ in boxes)
    assert max(box[3] for box, _ in boxes) == card.bottom


def test_confirmed_auth_stripe_is_one_solid_block():
    from types import SimpleNamespace
    from xducraft_bot.plugins.xducraft_mc_status import auth_mode as auth

    card = ir.CardLayout(node={"children": []}, level=0, top=0)
    resolved = SimpleNamespace(
        mode=auth.MODE_MUA,
        confirmed=True,
        conflict=False,
        style=auth.style_for(auth.MODE_MUA),
    )
    canvas = raster.Canvas(t.CANVAS_WIDTH, t.CARD_HEIGHT)
    boxes = []
    canvas.rect = lambda box, **kwargs: boxes.append((box, kwargs.get("fill")))  # type: ignore[assignment]
    ir._draw_auth_stripe(canvas, card, resolved)
    assert boxes == [((card.left, card.top, card.box_left, card.bottom), resolved.style.color)]


def test_named_textures_converge_to_black_concrete_brightness():
    after = []
    for name in ("bamboo_block.png", "dirt.png", "black_concrete_powder.png"):
        canvas = raster.Canvas(64, 64)
        canvas.tile_background(name)
        after.append(raster._mean_luminance(canvas.image))
    assert max(after) - min(after) < 0.004, after


def test_text_shadow_is_enabled_by_default():
    with_shadow = raster.Canvas(120, 40, background=(255, 255, 255))
    without_shadow = raster.Canvas(120, 40, background=(255, 255, 255))
    with_shadow.text("SHADOW", (8, 20), fonts.DATA, t.INK)
    without_shadow.text("SHADOW", (8, 20), fonts.DATA, t.INK, shadow=False)
    assert np.array(with_shadow.image).min() < 255
    assert np.array(without_shadow.image).min() == 255


def test_black_text_never_receives_a_shadow():
    default_shadow = raster.Canvas(120, 40, background=(255, 255, 255))
    shadow_disabled = raster.Canvas(120, 40, background=(255, 255, 255))
    default_shadow.text("BLACK", (8, 20), fonts.DATA, t.INK_DARK)
    shadow_disabled.text("BLACK", (8, 20), fonts.DATA, t.INK_DARK, shadow=False)
    assert np.array_equal(np.array(default_shadow.image), np.array(shadow_disabled.image))


@pytest.mark.parametrize(
    "description",
    [None, "", "A Minecraft Server", "A Minecraft Server (the default server motd)",
     {"text": "A Minecraft Server"}],
)
def test_empty_or_default_motd_falls_back_to_configured_remark(description):
    node = {"online": True, "comment": "配置备注名称", "description": description}
    text = "".join(segment.text for segment in ir._motd_segments(node))
    assert text == "配置备注名称"


def test_real_motd_replaces_remark_and_keeps_two_lines():
    node = {
        "online": True,
        "comment": "配置备注名称",
        "description": {"text": "第一行 MOTD\n第二行 MOTD"},
    }
    text = "".join(segment.text for segment in ir._motd_segments(node))
    assert text == "第一行 MOTD\n第二行 MOTD"
    assert "配置备注" not in text


def test_rainbow_remark_survives_default_motd_fallback():
    node = {
        "online": True,
        "description": "A Minecraft Server",
        "comment": "<gradient:#FF5555:#FFFF55:#55FF55:#5555FF>彩虹备注</gradient>",
    }
    segments = ir._motd_segments(node)
    assert segments and segments[0].gradient is not None
    assert len(segments[0].gradient) == 4


def test_all_tied_busiest_servers_receive_fire_at_five_or_more():
    nodes = [
        {"online": True, "players": {"online": 9}, "children": []},
        {"online": True, "players": {"online": 7}, "children": []},
        {"online": True, "players": {"online": 9}, "children": []},
        {"online": False, "players": {"online": 99}, "children": []},
    ]
    cards, _ = ir.build_layout(nodes, 0)
    hottest = ir._hottest_card_ids(list(ir._iter_cards(cards)))
    assert hottest == {id(nodes[0]), id(nodes[2])}


def test_no_fire_when_busiest_server_has_fewer_than_five_players():
    nodes = [
        {"online": True, "players": {"online": 4}, "children": []},
        {"online": True, "players": {"online": 4}, "children": []},
    ]
    cards, _ = ir.build_layout(nodes, 0)
    assert ir._hottest_card_ids(list(ir._iter_cards(cards))) == set()


def test_fire_icon_sits_immediately_left_of_player_counter():
    canvas = raster.Canvas(200, 60)
    pasted = []
    canvas.paste = lambda icon, x, y: pasted.append((icon, x, y))  # type: ignore[assignment]
    right = 180
    center_y = 30
    counter = "12/100"
    box = ir._draw_fire_by_player_count(canvas, right, center_y, counter)

    assert box is not None and len(pasted) == 1
    expected_right = right - canvas.measure(counter, fonts.DATA) - t.FIRE_ICON_GAP
    assert box[2] == expected_right
    assert box[3] - box[1] == t.FIRE_ICON_SIZE
    assert (box[1] + box[3]) / 2 == center_y - t.FIRE_ICON_RISE
    assert pasted[0][0].size == (t.px(t.FIRE_ICON_SIZE), t.px(t.FIRE_ICON_SIZE))
    assert t.FIRE_ICON_SIZE == t.TYPE_DATA