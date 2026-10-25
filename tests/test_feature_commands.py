from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import xducraft_features as features_module
from xducraft_bot.shared import feature_gate
from xducraft_bot.shared import permissions as permissions_module


class HandlerFinished(Exception):
    pass


@pytest.mark.asyncio
async def test_private_admin_can_disable_feature_for_selected_group(
    isolated_feature_gate,
    mocker,
):
    group_id = 123456789
    feature_gate.register(feature_gate.Feature(
        key="anti_recall",
        name="反撤回",
    ))
    mocker.patch.object(
        features_module,
        "can_manage_group",
        AsyncMock(return_value=True),
    )
    finish = mocker.patch.object(
        features_module.feature_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )
    args = MagicMock()
    args.extract_plain_text.return_value = f"{group_id} off 反撤回"
    event = MagicMock()
    event.user_id = 10001

    with pytest.raises(HandlerFinished):
        await features_module.handle_features(MagicMock(), event, args)

    assert feature_gate.resolve("anti_recall", group_id)[0] is False


@pytest.mark.asyncio
async def test_private_management_accepts_feature_names_with_spaces(
    isolated_feature_gate,
    mocker,
):
    group_id = 123456789
    feature_gate.register(feature_gate.Feature(
        key="multi_word_for_test",
        name="测试 多词功能",
    ))
    mocker.patch.object(
        features_module,
        "can_manage_group",
        AsyncMock(return_value=True),
    )
    finish = mocker.patch.object(
        features_module.feature_command,
        "finish",
        AsyncMock(side_effect=HandlerFinished),
    )
    args = MagicMock()
    args.extract_plain_text.return_value = f"{group_id} off 测试 多词功能"
    event = MagicMock()
    event.user_id = 10001

    with pytest.raises(HandlerFinished):
        await features_module.handle_features(MagicMock(), event, args)

    assert feature_gate.resolve("multi_word_for_test", group_id)[0] is False


@pytest.mark.asyncio
async def test_private_member_cannot_manage_selected_group(mocker):
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(return_value={"role": "member"})
    event = MagicMock()
    event.user_id = 10001
    mocker.patch.object(
        permissions_module,
        "is_superuser",
        AsyncMock(return_value=False),
    )

    allowed = await permissions_module.can_manage_group(
        bot,
        event,
        123456789,
    )

    assert allowed is False


@pytest.mark.asyncio
async def test_private_group_admin_can_manage_selected_group(mocker):
    bot = MagicMock()
    bot.get_group_member_info = AsyncMock(return_value={"role": "admin"})
    event = MagicMock()
    event.user_id = 10001
    mocker.patch.object(
        permissions_module,
        "is_superuser",
        AsyncMock(return_value=False),
    )

    allowed = await permissions_module.can_manage_group(
        bot,
        event,
        123456789,
    )

    assert allowed is True
    bot.get_group_member_info.assert_awaited_once_with(
        group_id=123456789,
        user_id=10001,
        no_cache=False,
    )


def test_new_feature_is_off_without_a_saved_group_preference(isolated_feature_gate):
    gate = isolated_feature_gate
    gate.register(gate.Feature(key="fresh_feature", name="新功能"))
    assert gate.resolve("fresh_feature", 10001) == (False, gate.SOURCE_DEFAULT)
    assert not gate.is_enabled("fresh_feature", 10001)


def test_sole_feature_write_mirrors_group_control_after_verified_custom_setter(
    isolated_feature_gate,
):
    from xducraft_bot.shared.configuration import (
        PluginConfiguration,
        declare_config,
        plugin_control,
        set_plugin_enabled,
    )

    gate = isolated_feature_gate
    state = {"enabled": False, "allowed": False}

    def setter(_group_id, enabled):
        if enabled and not state["allowed"]:
            raise ValueError("precondition")
        old = state["enabled"]
        state["enabled"] = enabled
        return old != enabled

    key = "verified_custom_feature"
    plugin_key = "verified_custom_owner"
    declare_config(PluginConfiguration(
        key=plugin_key,
        name="验证插件",
        feature_keys=(key,),
    ))
    gate.register(gate.Feature(
        key=key,
        name="验证功能",
        getter=lambda _group_id: state["enabled"],
        setter=setter,
    ))

    assert not gate.set_enabled(key, 10001, True)
    assert plugin_control(plugin_key, 10001)["enabled"] is False
    state["allowed"] = True
    assert gate.set_enabled(key, 10001, True)
    saved = plugin_control(plugin_key, 10001)
    assert saved["enabled"] is True
    assert saved["effective"] is False
    assert gate.resolve(key, 10001)[0] is True
    assert gate.is_enabled(key, 10001) is False
    set_plugin_enabled(plugin_key, True)
    assert plugin_control(plugin_key, 10001)["effective"] is True
    assert gate.is_enabled(key, 10001) is True


def test_unchanged_custom_setter_still_repairs_sole_feature_group_control(
    isolated_feature_gate,
):
    from xducraft_bot.shared.configuration import (
        PluginConfiguration,
        declare_config,
        plugin_control,
    )

    gate = isolated_feature_gate
    key = "unchanged_custom_feature"
    plugin_key = "unchanged_custom_owner"
    declare_config(PluginConfiguration(
        key=plugin_key,
        name="不变值插件",
        feature_keys=(key,),
    ))
    gate.register(gate.Feature(
        key=key,
        name="不变值功能",
        getter=lambda _group_id: True,
        setter=lambda _group_id, _enabled: False,
    ))
    assert gate.set_enabled(key, 10001, True)
    assert plugin_control(plugin_key, 10001)["enabled"] is True
