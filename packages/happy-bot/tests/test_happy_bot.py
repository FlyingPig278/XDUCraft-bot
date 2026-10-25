from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import xducraft_happy_bot as happy_module
from xducraft_bot.shared.config_store import ConfigDocumentStore
from xducraft_bot.shared.configuration import (
    ConfigContext,
    ConfigurationError,
    set_plugin_enabled,
)
from xducraft_happy_bot import data_manager as happy_data
from xducraft_happy_bot.configuration import bind_configuration


@pytest.fixture
def isolated_happy_storage(tmp_path, monkeypatch):
    store = ConfigDocumentStore(
        "happy_bot",
        happy_data._default_data,
        happy_data._normalize,
        database_path=str(tmp_path / "happy.sqlite3"),
    )
    monkeypatch.setattr(happy_data, "_store", store)
    return happy_data


def test_happy_declaration_only_changes_selected_group(isolated_happy_storage):
    happy = isolated_happy_storage
    happy.set_emoji_id("123", 10001)
    happy.set_emoji_id("456", 10002)
    declaration = bind_configuration(happy)
    assert set(declaration.resources) == {"group"}
    resource = declaration.resources["group"]
    resource.write(ConfigContext(10001), {"emoji_id": "789"})
    assert happy.get_emoji_id(10001) == "789"
    assert happy.get_emoji_id(10002) == "456"
    assert happy.get_emoji_id(10003) == happy.DEFAULT_EMOJI_ID
    before = resource.read(ConfigContext(10002))
    for invalid in (None, "", "not-a-number"):
        with pytest.raises(ConfigurationError):
            resource.write(ConfigContext(10001), {"emoji_id": invalid})
    assert happy.get_emoji_id(10001) == "789"
    assert resource.read(ConfigContext(10002)).revision_values == before.revision_values


@pytest.mark.asyncio
async def test_reaction_handler_obeys_global_and_group_gates_with_group_emoji(
    isolated_happy_storage,
    isolated_feature_gate,
    enable_plugin,
):
    group_id = 10001
    other_group_id = 10002
    gate = isolated_feature_gate
    gate.register(gate.Feature(
        key=happy_module.FEATURE_KEY,
        name="表情回应",
        description="被 @ 或被回复时自动贴表情",
        passive=True,
    ))

    isolated_happy_storage.set_emoji_id("789", group_id)
    isolated_happy_storage.set_emoji_id("456", other_group_id)
    bot = SimpleNamespace(call_api=AsyncMock())
    event = SimpleNamespace(group_id=group_id, message_id=901)
    other_event = SimpleNamespace(group_id=other_group_id, message_id=902)

    # The global gate is initially off.
    await happy_module.handle_at_me(bot, event)
    bot.call_api.assert_not_awaited()

    # Global enablement alone does not opt any group into this passive feature.
    enable_plugin("happy_bot")
    await happy_module.handle_at_me(bot, event)
    bot.call_api.assert_not_awaited()

    assert gate.set_enabled(happy_module.FEATURE_KEY, group_id, True)
    assert gate.is_enabled(happy_module.FEATURE_KEY, group_id)
    assert not gate.is_enabled(happy_module.FEATURE_KEY, other_group_id)
    await happy_module.handle_at_me(bot, event)
    bot.call_api.assert_awaited_once_with(
        "set_msg_emoji_like",
        message_id=901,
        emoji_id="789",
        set=True,
    )

    # Another group's saved emoji must not opt that group into reactions.
    await happy_module.handle_at_me(bot, other_event)
    assert bot.call_api.await_count == 1

    set_plugin_enabled("happy_bot", False, actor="test")
    await happy_module.handle_at_me(bot, event)
    assert bot.call_api.await_count == 1
