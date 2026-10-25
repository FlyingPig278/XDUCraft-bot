from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from xducraft_mc_status.status_fetcher import (
    _sanitize_description,
    get_single_server_status,
)


def test_normalize_description_keeps_text_and_html_structure():
    raw_description = {
        "text": "",
        "extra": [
            {"color": "#FFAA00", "text": "Hello"},
            {"text": "\n"},
            {"text": "World"},
        ],
    }

    normalized = _sanitize_description(raw_description)

    assert normalized["text"] == "Hello\nWorld"
    assert normalized["html"] == '<font color="#FFAA00">Hello</font><br>World'


@pytest.mark.asyncio
async def test_get_single_server_status_preserves_hex_colors(mocker):
    raw_description = {
        "text": "",
        "extra": [
            {"color": "#FFAA00", "text": "Hello"},
            {"text": "\n"},
            {"color": "#12AB34", "text": "XDUCraft"},
        ],
    }
    fake_status = {
        "online": True,
        "hostname": "resolved.example.com",
        "port": 25570,
        "ping": 13,
        "version": "Paper 1.21.1",
        "protocol": 767,
        "players": {
            "online": 2,
            "max": 20,
            "sample": [
                {"name": "Alice", "id": "uuid-alice"},
                {"name": "Bob", "id": "uuid-bob"},
            ],
        },
        "description_raw": raw_description,
        "description": {
            "text": "Hello\nXDUCraft",
            "html": '<font color="#FFAA00">Hello</font><br><font color="#12AB34">XDUCraft</font>',
        },
        "favicon": "data:image/png;base64,abc",
    }

    mocker.patch(
        "xducraft_mc_status.status_fetcher.mc_protocol.query_status",
        AsyncMock(return_value=fake_status),
    )

    result = await get_single_server_status("mc.example.com:25570")

    assert result["online"] is True
    assert result["ip"] == "mc.example.com:25570"
    assert result["original_query"] == "mc.example.com:25570"
    assert result["hostname"] == "resolved.example.com"
    assert result["port"] == 25570
    assert result["ping"] == 13
    assert result["version"] == "Paper 1.21.1"
    assert result["protocol"] == 767
    assert result["players"] == {
        "online": 2,
        "max": 20,
        "sample": [
            {"name": "Alice", "id": "uuid-alice"},
            {"name": "Bob", "id": "uuid-bob"},
        ],
    }
    assert result["description"] == {
        "text": "Hello\nXDUCraft",
        "html": '<font color="#FFAA00">Hello</font><br><font color="#12AB34">XDUCraft</font>',
    }
    assert result["favicon"] == "data:image/png;base64,abc"


@pytest.mark.asyncio
async def test_get_single_server_status_returns_ping_from_protocol(mocker):
    fake_status = {
        "online": True,
        "hostname": "resolved.example.com",
        "port": 25565,
        "ping": 15,
        "version": "Paper 1.21.1",
        "protocol": 767,
        "players": {"online": 0, "max": 20, "sample": []},
        "description": {"text": "XDUCraft"},
    }

    query_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher.mc_protocol.query_status",
        AsyncMock(return_value=fake_status),
    )

    result = await get_single_server_status("mc.example.com")

    assert result["online"] is True
    assert result["ping"] == 15
    query_mock.assert_awaited_once_with("mc.example.com", timeout=3.0)


@pytest.mark.asyncio
async def test_get_single_server_status_returns_offline_payload_on_failure(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.mc_protocol.query_status",
        AsyncMock(side_effect=TimeoutError("direct timed out")),
    )

    result = await get_single_server_status("mc.example.com:25570")

    assert result["online"] is False
    assert result["hostname"] == "mc.example.com"
    assert result["port"] == 25570
    assert result["ip"] == "mc.example.com:25570"
    assert result["original_query"] == "mc.example.com:25570"
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_get_single_server_status_uses_sjtu_source_when_configured(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="sjtu",
    )
    sjtu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com"}),
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com"}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    sjtu_mock.assert_awaited_once_with("mc.example.com")
    protocol_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_single_server_status_uses_jsu_source_when_configured(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="jsu",
    )
    jsu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_jsu",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 17}),
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com"}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 17
    jsu_mock.assert_awaited_once_with("mc.example.com")
    protocol_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_single_server_status_auto_fallback_to_sjtu(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="auto",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="",
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "timeout"}),
    )
    jsu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_jsu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "jsu timeout"}),
    )
    sjtu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 12}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 12
    protocol_mock.assert_awaited_once_with("mc.example.com")
    jsu_mock.assert_awaited_once_with("mc.example.com")
    sjtu_mock.assert_awaited_once_with("mc.example.com")


@pytest.mark.asyncio
async def test_get_single_server_status_auto_keeps_protocol_result_when_both_fail(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="auto",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "protocol timeout"}),
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_jsu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "jsu timeout"}),
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "sjtu timeout"}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is False
    assert "protocol: protocol timeout" in result["error"]
    assert "jsu: jsu timeout" in result["error"]
    assert "sjtu: sjtu timeout" in result["error"]


@pytest.mark.asyncio
async def test_get_single_server_status_uses_custom_source_when_configured(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="custom",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="https://api.example.com/status",
    )
    custom_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_custom",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 19}),
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 19
    custom_mock.assert_awaited_once_with("mc.example.com", "https://api.example.com/status")
    protocol_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_single_server_status_auto_fallback_to_custom_before_sjtu(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="auto",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="https://api.example.com/status",
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "protocol timeout"}),
    )
    custom_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_custom",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 25}),
    )
    sjtu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 12}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 25
    protocol_mock.assert_awaited_once_with("mc.example.com")
    custom_mock.assert_awaited_once_with("mc.example.com", "https://api.example.com/status")
    sjtu_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_single_server_status_custom_retries_without_tls_verify_on_cert_error(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="custom",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="https://api.example.com/status",
    )

    request_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._request_custom",
        AsyncMock(side_effect=[
            Exception("[SSL: CERTIFICATE_VERIFY_FAILED] self signed certificate"),
            {"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 31},
        ]),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 31
    assert result["tls_verify_bypassed"] is True
    assert request_mock.await_count == 2


@pytest.mark.asyncio
async def test_get_single_server_status_auto_api_first_uses_sjtu_before_protocol(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="auto_api_first",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="",
    )
    sjtu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 12}),
    )
    jsu_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_jsu",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 9}),
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 88}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 12
    sjtu_mock.assert_awaited_once_with("mc.example.com")
    jsu_mock.assert_not_called()
    protocol_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_single_server_status_auto_api_first_falls_back_to_protocol(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="auto_api_first",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "sjtu timeout"}),
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_jsu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "jsu timeout"}),
    )
    protocol_mock = mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": True, "ip": "mc.example.com", "original_query": "mc.example.com", "ping": 88}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is True
    assert result["ping"] == 88
    protocol_mock.assert_awaited_once_with("mc.example.com")


@pytest.mark.asyncio
async def test_get_single_server_status_auto_api_first_returns_first_result_when_all_fail(mocker):
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_source",
        return_value="auto_api_first",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher.data_manager.get_group_status_api_url",
        return_value="",
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_sjtu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "sjtu timeout"}),
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_jsu",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "jsu timeout"}),
    )
    mocker.patch(
        "xducraft_mc_status.status_fetcher._fetch_via_protocol",
        AsyncMock(return_value={"online": False, "ip": "mc.example.com", "original_query": "mc.example.com", "error": "protocol timeout"}),
    )

    result = await get_single_server_status("mc.example.com", group_id=114514)

    assert result["online"] is False
    assert result["source"] == "auto_api_first"
    assert "jsu: jsu timeout" in result["error"]
    assert "protocol: protocol timeout" in result["error"]
