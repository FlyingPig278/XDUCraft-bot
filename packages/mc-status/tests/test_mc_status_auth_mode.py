from __future__ import annotations

import httpx
import pytest

from xducraft_mc_status import auth_mode as auth
from xducraft_mc_status import config_coder


def _lookup(
    *,
    profiles: dict[str, str] | None = None,
    completed: set[str] | None = None,
) -> auth.ProfileLookup:
    normalized_profiles = {
        name.lower(): auth.normalize_uuid(player_uuid)
        for name, player_uuid in (profiles or {}).items()
    }
    normalized_completed = {
        name.lower()
        for name in (completed if completed is not None else normalized_profiles.keys())
    }
    return auth.ProfileLookup(normalized_profiles, frozenset(normalized_completed))


def test_auth_mode_codes_append_xdu_without_reordering_legacy_codes():
    assert {
        auth.MODE_OFFICIAL: auth.mode_to_code(auth.MODE_OFFICIAL),
        auth.MODE_MUA: auth.mode_to_code(auth.MODE_MUA),
        auth.MODE_YGGDRASIL: auth.mode_to_code(auth.MODE_YGGDRASIL),
        auth.MODE_OFFLINE: auth.mode_to_code(auth.MODE_OFFLINE),
        auth.MODE_MIXED: auth.mode_to_code(auth.MODE_MIXED),
        auth.MODE_XDU: auth.mode_to_code(auth.MODE_XDU),
    } == {
        "official": 1,
        "mua": 2,
        "yggdrasil": 3,
        "offline": 4,
        "mixed": 5,
        "xdu": 6,
    }
    assert auth.code_to_mode(6) == auth.MODE_XDU


def test_legacy_compact_config_without_auth_field_still_decodes():
    legacy_servers = [[
        "legacy.example.com",
        "旧配置",
        "生存",
        "2ECC71",
        0,
        1,
        "公开名称",
        0,
    ]]

    decoded = config_coder._compact_array_to_json(legacy_servers)

    assert decoded[0]["ip"] == "legacy.example.com"
    assert decoded[0]["hide_ip"] is True
    assert decoded[0]["display_name"] == "公开名称"
    assert decoded[0]["auth_mode"] == ""


def test_xdu_mode_round_trips_through_current_compact_config():
    encoded = config_coder.compress_config({
        "footer": "测试",
        "show_offline_by_default": False,
        "servers": [{"ip": "xdu.example.com", "auth_mode": auth.MODE_XDU}],
    })

    decoded = config_coder.decompress_config(encoded)

    assert decoded is not None
    assert decoded["servers"][0]["auth_mode"] == auth.MODE_XDU


async def test_xdu_lookup_uses_current_yggdrasil_endpoint():
    seen_requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json=[{"name": "Alice", "id": "12345678123456781234567812345678"}],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await auth._lookup_uncached(auth.SOURCE_XDU, ["Alice"], client)

    assert auth.XDU_YGGDRASIL_ROOT == "https://www.xducraft.cn/api/yggdrasil"
    assert len(seen_requests) == 1
    assert str(seen_requests[0].url) == (
        "https://www.xducraft.cn/api/yggdrasil/api/profiles/minecraft"
    )
    assert result == {"alice": "12345678123456781234567812345678"}


async def test_detection_keeps_xdu_and_mua_union_overlap_ambiguous(monkeypatch):
    player_uuid = "12345678123456781234567812345678"
    lookups = {
        auth.SOURCE_XDU: _lookup(profiles={"Alice": player_uuid}),
        auth.SOURCE_MUA: _lookup(profiles={"Alice": player_uuid}),
        auth.SOURCE_MOJANG: _lookup(completed={"Alice"}),
    }

    async def fake_lookup(source, names, client):
        return lookups[source]

    monkeypatch.setattr(auth, "lookup_profiles", fake_lookup)
    verdict = await auth.detect_auth_mode([{"name": "Alice", "id": player_uuid}])

    assert verdict.mode == auth.MODE_UNKNOWN
    assert verdict.counts == {auth.MODE_UNKNOWN: 1}
    assert verdict.partial is True


@pytest.mark.parametrize(
    ("matched_source", "expected_mode"),
    [
        (auth.SOURCE_XDU, auth.MODE_XDU),
        (auth.SOURCE_MUA, auth.MODE_MUA),
        (auth.SOURCE_MOJANG, auth.MODE_OFFICIAL),
    ],
)
async def test_detection_matches_other_known_sources(
    monkeypatch,
    matched_source: str,
    expected_mode: str,
):
    player_uuid = "12345678123456781234567812345678"
    lookups = {
        source: _lookup(
            profiles={"Alice": player_uuid} if source == matched_source else None,
            completed={"Alice"},
        )
        for source in (auth.SOURCE_XDU, auth.SOURCE_MUA, auth.SOURCE_MOJANG)
    }

    async def fake_lookup(source, names, client):
        return lookups[source]

    monkeypatch.setattr(auth, "lookup_profiles", fake_lookup)
    verdict = await auth.detect_auth_mode([{"name": "Alice", "id": player_uuid}])

    assert verdict.mode == expected_mode
    assert verdict.partial is False


async def test_detection_only_calls_unknown_station_when_all_sources_completed(monkeypatch):
    player_uuid = "12345678123456781234567812345678"
    lookups = {
        auth.SOURCE_XDU: _lookup(completed={"Alice"}),
        auth.SOURCE_MUA: _lookup(completed={"Alice"}),
        auth.SOURCE_MOJANG: _lookup(completed={"Alice"}),
    }

    async def fake_lookup(source, names, client):
        return lookups[source]

    monkeypatch.setattr(auth, "lookup_profiles", fake_lookup)
    verdict = await auth.detect_auth_mode([{"name": "Alice", "id": player_uuid}])

    assert verdict.mode == auth.MODE_YGGDRASIL
    assert verdict.partial is False

    lookups[auth.SOURCE_MUA] = _lookup()
    verdict = await auth.detect_auth_mode([{"name": "Alice", "id": player_uuid}])

    assert verdict.mode == auth.MODE_UNKNOWN
    assert verdict.partial is True


async def test_offline_uuid_is_detected_without_external_requests(monkeypatch):
    async def fail_if_called(source, names, client):
        raise AssertionError("离线 UUID 不应触发外部请求")

    monkeypatch.setattr(auth, "lookup_profiles", fail_if_called)
    verdict = await auth.detect_auth_mode(
        [{"name": "OfflineAlice", "id": auth.offline_uuid("OfflineAlice")}]
    )

    assert verdict.mode == auth.MODE_OFFLINE
    assert verdict.partial is False
