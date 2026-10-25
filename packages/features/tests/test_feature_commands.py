from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import xducraft_features as features_module
from xducraft_bot.shared import feature_gate


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


