"""统一的功能开关面板。

每个插件都自己实现一套 ``on/off`` 之后，管理员想知道“这个群到底开了什么”
就得挨个敲一遍指令。这个插件把 :mod:`xducraft_bot.shared.feature_gate` 里
注册过的功能集中列出来，一条命令看全、一条命令开关。

指令::

    /功能              查看本群所有功能的开关状态
    /功能 on <名字>     开启
    /功能 off <名字>    关闭
    /功能 reset <名字>  清除本群配置，回到默认值
    /功能 default on|off <名字>   设置全局默认（SUPERUSER）
"""

from __future__ import annotations

from typing import Optional

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.permissions import can_manage, is_superuser

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_features",
    description="集中查看与开关本群的各项机器人功能",
    usage="/功能 — 查看本群功能开关；/功能 on|off <名字> — 开关",
)

feature_command = on_command("功能", aliases={"features", "feature", "开关"}, priority=10, block=True)


def _resolve_feature(token: str) -> Optional[feature_gate.Feature]:
    """按 key 或中文名找功能，都支持大小写/空格容错。"""
    needle = token.strip().lower()
    for feature in feature_gate.all_features():
        if feature.key.lower() == needle or feature.name.lower() == needle:
            return feature
    # 再试一次前缀匹配，方便只敲前几个字。
    matches = [
        feature for feature in feature_gate.all_features()
        if feature.key.lower().startswith(needle) or feature.name.startswith(token.strip())
    ]
    return matches[0] if len(matches) == 1 else None


def _known_features_text() -> str:
    lines = [f"  {feature.key} — {feature.name}" for feature in feature_gate.all_features()]
    return "可用的功能名：\n" + "\n".join(lines) if lines else "当前没有注册任何功能。"


@feature_command.handle()
async def handle_features(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await feature_command.finish("请在群里使用 /功能 查看和配置本群的功能开关。")

    tokens = args.extract_plain_text().strip().split()
    group_id = event.group_id

    if not tokens:
        await feature_command.finish(_render_overview(group_id))

    action = tokens[0].lower()

    if action in {"default", "默认"}:
        if not await is_superuser(bot, event):
            await feature_command.finish("设置全局默认值需要超级用户权限。")
        if len(tokens) != 3 or tokens[1].lower() not in {"on", "off"}:
            await feature_command.finish("用法：/功能 default on|off <功能名>")
        feature = _resolve_feature(tokens[2])
        if feature is None:
            await feature_command.finish(f"没有找到功能「{tokens[2]}」。\n{_known_features_text()}")
        if not feature.uses_shared_store:
            await feature_command.finish(
                f"「{feature.name}」使用插件自己的开关配置，不支持设置全局默认值。"
            )
        enabled = tokens[1].lower() == "on"
        feature_gate.set_default(feature.key, enabled)
        await feature_command.finish(
            f"已将「{feature.name}」的全局默认设为{'开启' if enabled else '关闭'}。\n"
            "（只影响没有单独配置过的群）"
        )

    if not await can_manage(bot, event):
        await feature_command.finish("只有群管理员可以修改功能开关。发送 /功能 可以查看当前状态。")

    if action in {"on", "off", "开", "关", "reset", "重置"}:
        if len(tokens) < 2:
            await feature_command.finish(f"用法：/功能 {action} <功能名>\n{_known_features_text()}")

        feature = _resolve_feature(tokens[1])
        if feature is None:
            await feature_command.finish(f"没有找到功能「{tokens[1]}」。\n{_known_features_text()}")

        if feature.superuser_only and not await is_superuser(bot, event):
            await feature_command.finish(f"「{feature.name}」只有超级用户可以修改。")

        if action in {"reset", "重置"}:
            if not feature.uses_shared_store:
                await feature_command.finish(
                    f"「{feature.name}」使用插件自己的开关配置，没有可清除的默认值覆盖。"
                )
            if feature_gate.clear_override(feature.key, group_id):
                enabled, _ = feature_gate.resolve(feature.key, group_id)
                await feature_command.finish(
                    f"已清除「{feature.name}」的本群配置，现在跟随默认值：{'开启' if enabled else '关闭'}"
                )
            await feature_command.finish(f"「{feature.name}」本群本来就没有单独配置。")

        enabled = action in {"on", "开"}
        changed = feature_gate.set_enabled(feature.key, group_id, enabled)
        state = "开启" if enabled else "关闭"
        if changed:
            await feature_command.finish(f"已{state}「{feature.name}」。")
        await feature_command.finish(f"「{feature.name}」已经是{state}状态。")

    await feature_command.finish(
        "用法：\n"
        "/功能 — 查看本群所有功能状态\n"
        "/功能 on <功能名> — 开启\n"
        "/功能 off <功能名> — 关闭\n"
        "/功能 reset <功能名> — 回到默认值\n"
        f"\n{_known_features_text()}"
    )


def _render_overview(group_id: int) -> str:
    snapshot = feature_gate.describe_group(group_id)
    if not snapshot:
        return "当前没有注册任何可开关的功能。"

    lines = ["本群功能开关："]
    for item in snapshot:
        mark = "✅" if item["enabled"] else "⬜"
        source = "本群配置" if item["source"] == feature_gate.SOURCE_GROUP else "默认值"
        passive = "（被动触发）" if item["passive"] else ""
        restricted = "（仅超级用户可改）" if item["superuser_only"] else ""
        lines.append(f"{mark} {item['name']} [{item['key']}] · {source}{passive}{restricted}")
        if item["description"]:
            lines.append(f"     {item['description']}")

    lines.append("")
    lines.append("管理员可用 /功能 on <功能名> 开启，/功能 off <功能名> 关闭。")
    lines.append("被动触发的功能默认关闭，开启后才会在本群自动响应。")
    return "\n".join(lines)
