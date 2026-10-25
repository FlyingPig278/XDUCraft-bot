from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from xducraft_mc_status import handlers


@pytest.mark.asyncio
async def test_query_all_sends_progress_before_fetching(mocker, enable_plugin):
    from xducraft_bot.shared import feature_gate

    enable_plugin("mc_status", 123456789)
    feature_gate.set_enabled("mc_status", 123456789, True)
    order = []
    matcher = MagicMock()
    matcher.send = AsyncMock(side_effect=lambda *_: order.append("progress"))
    matcher.finish = AsyncMock(side_effect=lambda *_: order.append("result"))
    mocker.patch.object(handlers, "_matcher", return_value=matcher)
    mocker.patch.object(
        handlers,
        "get_server_list",
        return_value=[{"ip": "mc.example.com"}],
    )
    mocker.patch.object(
        handlers,
        "get_group_status_api_source",
        return_value="protocol",
    )

    async def fetch(_group_id):
        order.append("fetch")
        return [{"online": True}]

    mocker.patch.object(handlers, "get_all_servers_status", side_effect=fetch)
    mocker.patch.object(
        handlers,
        "render_status_image",
        AsyncMock(return_value="E:/tmp/status.png"),
    )
    event = MagicMock()
    event.group_id = 123456789

    await handlers.handle_query_all(MagicMock(), event, False)

    assert order == ["progress", "fetch", "result"]
