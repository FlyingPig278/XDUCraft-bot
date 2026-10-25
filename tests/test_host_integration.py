"""Host-level contract between separately installed Admin, Core and Pig packages."""
from types import SimpleNamespace

import httpx
import nonebot
import pytest

from xducraft_admin.adapters import discover_catalog
from xducraft_admin.app import create_app
from xducraft_admin.auth import AdminAuth
from xducraft_admin.service import AdminService


@pytest.mark.asyncio
async def test_panel_changes_reach_business_reader_and_respect_global_stop(
    tmp_path, isolated_feature_gate,
):
    plugin = nonebot.load_plugin("xducraft_pig_bot")
    assert plugin is not None
    from xducraft_pig_bot import pig_data_manager

    service = AdminService(
        lambda: discover_catalog([plugin]), isolated_feature_gate,
        SimpleNamespace(), lambda: {},
    )
    password = "integration-only-long-password"
    app = create_app(service, AdminAuth(password), tmp_path / "missing-static")
    origin = "http://127.0.0.1:18765"
    path = "/api/groups/10001/config/pig_bot"
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url=origin) as client:
        denied = await client.get(path)
        assert denied.status_code == 401
        assert pig_data_manager.get_max_forward_results(10001) == 5
        login = await client.post(
            "/api/auth/login", json={"password": password},
            headers={"Origin": origin},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        write_headers = {"Origin": origin, "X-CSRF-Token": csrf}
        initial = (await client.get(path)).json()
        saved = await client.put(
            path, json={"max_forward_results": 9},
            headers={**write_headers, "If-Match": initial["revision"]},
        )
        assert saved.status_code == 200
        assert pig_data_manager.get_max_forward_results(10001) == 9
        assert pig_data_manager.get_max_forward_results(10002) == 5
        stale = await client.put(
            path, json={"max_forward_results": 2},
            headers={**write_headers, "If-Match": initial["revision"]},
        )
        assert stale.status_code == 409
        assert pig_data_manager.get_max_forward_results(10001) == 9

        async def switch(control_path, enabled):
            current = (await client.get(control_path)).json()
            response = await client.put(
                control_path, json={"enabled": enabled},
                headers={**write_headers, "If-Match": current["revision"]},
            )
            assert response.status_code == 200
            return response.json()

        group_control = "/api/groups/10001/plugins/pig_bot/enabled"
        selected = await switch(group_control, True)
        assert selected["config"]["enabled"] is True
        assert selected["meta"]["effective"] is False
        await switch("/api/plugins/pig_bot/enabled", True)
        pig_data_manager.set_query_enabled(10001, True)
        assert isolated_feature_gate.is_enabled("pig_query", 10001)
        assert not isolated_feature_gate.is_enabled("pig_query", 10002)
        await switch("/api/plugins/pig_bot/enabled", False)
        assert not isolated_feature_gate.is_enabled("pig_query", 10001)
        stopped = (await client.get(group_control)).json()
        assert stopped["config"]["enabled"] is True
        assert stopped["meta"]["effective"] is False
        assert pig_data_manager.get_max_forward_results(10001) == 9
