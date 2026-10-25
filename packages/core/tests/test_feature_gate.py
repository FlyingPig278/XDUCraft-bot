from xducraft_bot.shared.configuration import (
    PluginConfiguration,
    declare_config,
    plugin_control,
    set_plugin_enabled,
)


def test_new_feature_is_off_without_a_saved_group_preference(isolated_feature_gate):
    gate = isolated_feature_gate
    gate.register(gate.Feature(key="fresh_feature", name="新功能"))
    assert gate.resolve("fresh_feature", 10001) == (False, gate.SOURCE_DEFAULT)
    assert not gate.is_enabled("fresh_feature", 10001)


def test_sole_feature_write_mirrors_group_control_after_verified_custom_setter(
    isolated_feature_gate,
):
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
