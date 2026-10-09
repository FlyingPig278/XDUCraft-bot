from __future__ import annotations

import asyncio
import copy
import json
import signal
import socket
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from PIL import Image
from pydantic import BaseModel, Field

from xducraft_bot.admin.adapters import DeploymentContext, PluginAdapter
from xducraft_bot.admin.app import COOKIE, create_app
from xducraft_bot.admin.auth import AdminAuth, SESSION_LIFETIME_SECONDS
from xducraft_bot.admin.server import AdminServer, AdminServerError
from xducraft_bot.admin.service import AdminService
from xducraft_bot.admin.avatars import AVATAR_MAX_BYTES, GroupAvatarCache
from xducraft_bot.plugins.xducraft_anti_recall.data_manager import AntiRecallStore
from xducraft_bot.plugins.xducraft_happy_bot import data_manager as happy_dm
from xducraft_bot.plugins.xducraft_invite.data_manager import InviteStore
from xducraft_bot.plugins.xducraft_invite.settings import InviteSettings
from xducraft_bot.plugins.xducraft_keyword import data_manager as keyword_dm
from xducraft_bot.plugins.xducraft_keyword.reply_codec import restore_reply
from xducraft_bot.plugins.xducraft_mc_status import data_manager as mc_dm
from xducraft_bot.plugins.xducraft_pig_bot.data_manager import DataManager as PigDataManager
from xducraft_bot.plugins.xducraft_wordcloud.data_manager import ChatLogDataManager
from xducraft_bot.shared import deployment_config as deployment
from xducraft_bot.shared.json_store import JsonStore


GROUP_A = 10001
GROUP_B = 10002
CONFIG_ONLY_GROUP = 30003
PASSWORD = "管理员-十二字符口令-安全"
BASE_URL = "http://127.0.0.1:18765"
ORIGIN_HEADERS = {"Origin": BASE_URL}


class MCDeploymentConfig(BaseModel):
    mcs_brand: str = "Environment Brand"
    mcs_title: str = "Environment Title"
    mcs_credit: str = "Environment Credit"
    mcs_show_generated_at: bool = True
    mcs_texture: str = ""
    mcs_width: int = 640
    mcs_scale: int = 2
    mcs_min_height: int = 0


class InviteDeploymentConfig(BaseModel):
    invite_group_id: int = GROUP_A
    invite_api_url: str = "https://example.test/invite"
    invite_api_secret: str = "active-secret-do-not-disclose"


class FriendDeploymentConfig(BaseModel):
    auto_accept_friend_group_ids: list[int] = Field(default_factory=lambda: [GROUP_A])


class SyntheticBot:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fail = False

    async def get_group_list(self) -> list[dict[str, object]]:
        if self.fail:
            raise RuntimeError("synthetic disconnect")
        return copy.deepcopy(self.rows)


@dataclass
class AdminEnvironment:
    app: Any
    client: httpx.AsyncClient
    service: AdminService
    auth: AdminAuth
    clock: list[float]
    bots: dict[str, SyntheticBot]
    feature_gate: Any
    happy_path: Path
    pig: PigDataManager
    wordcloud: ChatLogDataManager
    anti_recall: AntiRecallStore
    invite: InviteStore


async def _login(env: AdminEnvironment, password: str = PASSWORD) -> httpx.Response:
    return await env.client.post(
        "/api/auth/login",
        json={"password": password},
        headers=ORIGIN_HEADERS,
    )


def _write_headers(csrf: str, revision: str | None = None) -> dict[str, str]:
    headers = {**ORIGIN_HEADERS, "X-CSRF-Token": csrf}
    if revision is not None:
        headers["If-Match"] = revision
    return headers


def _error_code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (2, 2), (25, 100, 180, 255)).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
async def admin_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_feature_gate: Any,
) -> AdminEnvironment:
    feature_gate = isolated_feature_gate

    mc_store = JsonStore(
        str(tmp_path / "mc" / "server_data.json"),
        lambda: {mc_dm.GLOBAL_CONFIG_KEY: mc_dm._default_global_config()},
        mc_dm._normalize_data,
    )
    monkeypatch.setattr(mc_dm, "_store", mc_store)

    keyword_store = JsonStore(
        str(tmp_path / "keyword" / "keyword_config.json"),
        keyword_dm._default_config,
        keyword_dm._normalize_config,
    )
    keyword_media = tmp_path / "keyword" / "media"
    monkeypatch.setattr(keyword_dm, "_store", keyword_store)
    monkeypatch.setattr(keyword_dm, "MEDIA_DIR", str(keyword_media))

    happy_path = tmp_path / "happy" / "emoji_like_config.json"
    happy_store = JsonStore(str(happy_path), happy_dm._default_data, happy_dm._normalize)
    monkeypatch.setattr(happy_dm, "_store", happy_store)
    happy_dm.set_emoji_id("111")

    pig_dir = tmp_path / "pig"
    pig = PigDataManager(str(pig_dir), str(pig_dir / "pig.json"))
    wordcloud_dir = tmp_path / "wordcloud"
    wordcloud = ChatLogDataManager(
        str(wordcloud_dir),
        str(wordcloud_dir / "wordcloud.db"),
        str(wordcloud_dir / "wordcloud.json"),
    )
    anti_dir = tmp_path / "anti"
    anti_recall = AntiRecallStore(
        str(anti_dir / "anti.db"),
        str(anti_dir / "anti.json"),
        str(anti_dir / "media"),
    )
    invite = InviteStore(str(tmp_path / "invite" / "invite.db"))
    invite_settings = InviteSettings(
        group_id=GROUP_A,
        api_url="https://example.test/invite",
        api_secret="active-secret-do-not-disclose",
    )

    deployment_path = tmp_path / "deployment" / "deployment_overrides.json"
    monkeypatch.setattr(deployment, "DEPLOYMENT_OVERRIDES_PATH", deployment_path)
    monkeypatch.setattr(deployment, "_STORE", JsonStore(str(deployment_path), dict))
    monkeypatch.setattr(deployment, "_LOCK", RLock())
    monkeypatch.setattr(deployment, "_STARTUP_READY", False)
    monkeypatch.setattr(deployment, "_STARTUP_OVERRIDES", {})
    monkeypatch.setattr(deployment, "_STARTUP_ERROR", None)
    monkeypatch.setattr(deployment, "_STARTUP_BASES", {})
    deployment.apply_startup_overrides(MCDeploymentConfig())
    deployment.apply_startup_overrides(InviteDeploymentConfig())
    deployment.apply_startup_overrides(FriendDeploymentConfig())

    mc_settings = SimpleNamespace(
        brand="Environment Brand",
        title="Environment Title",
        credit="Environment Credit",
        show_generated_at=True,
        texture="",
        width=640,
        scale=2,
        min_height=0,
    )
    mc_settings_module = SimpleNamespace(
        Config=MCDeploymentConfig,
        SETTINGS=mc_settings,
        normalize_width=lambda value: int(value),
        normalize_scale=lambda value: int(value),
        normalize_min_height=lambda value: int(value),
    )
    invite_settings_module = SimpleNamespace(
        Config=InviteDeploymentConfig,
        SETTINGS=invite_settings,
        DEFAULT_API_URL="https://example.test/invite",
    )
    friend_settings_module = SimpleNamespace(
        Config=FriendDeploymentConfig,
        SETTINGS=SimpleNamespace(group_ids=(GROUP_A,)),
    )

    feature_gate.register(feature_gate.Feature(
        key="mc_status", name="MC 状态", default_enabled=True,
    ))
    feature_gate.register(feature_gate.Feature(
        key="keyword_reply", name="关键词回复", default_enabled=True,
    ))
    feature_gate.register(feature_gate.Feature(
        key="emoji_reaction", name="表情回应", default_enabled=False, passive=True,
    ))
    feature_gate.register(feature_gate.Feature(
        key="anti_recall", name="反撤回", default_enabled=True,
    ))
    feature_gate.register(feature_gate.Feature(
        key="auto_accept_friend", name="自动好友", default_enabled=True,
    ))
    feature_gate.register(feature_gate.Feature(
        key="pig_query", name="猪猪图查询",
        getter=lambda gid: pig.get_group_config(gid)["query_enabled"],
        setter=pig.set_query_enabled,
        lister=pig.list_configured_groups,
    ))
    feature_gate.register(feature_gate.Feature(
        key="pig_auto_push", name="猪猪图推送", passive=True,
        getter=lambda gid: pig.get_group_config(gid)["auto_push_enabled"],
        setter=pig.set_auto_push_enabled,
        lister=pig.list_auto_push_groups,
    ))
    feature_gate.register(feature_gate.Feature(
        key="wordcloud", name="词云",
        getter=wordcloud.is_group_enabled,
        setter=wordcloud.set_group_enabled,
        lister=wordcloud.get_enabled_groups,
    ))

    def put_mc(gid: int, data: dict[str, Any]) -> dict[str, Any]:
        if not mc_dm.import_group_data(gid, data):
            raise ValueError("mc_write_failed")
        return mc_dm.export_group_data(gid)

    def put_happy(gid: int, data: dict[str, Any]) -> dict[str, Any]:
        if data["emoji_id"] is None:
            happy_dm.clear_group_emoji_id(gid)
        else:
            happy_dm.set_emoji_id(data["emoji_id"], group_id=gid)
        return {
            "emoji_id": happy_dm.get_group_emoji_id(gid),
            "effective_emoji_id": happy_dm.get_emoji_id(gid),
        }

    def put_pig(data: dict[str, Any]) -> dict[str, Any]:
        pig.set_max_forward_results(data["max_forward_results"])
        return {"max_forward_results": pig.get_max_forward_results()}

    adapters = {
        "mc_status": PluginAdapter(
            "xducraft_mc_status", "MC 服务器状态", True, ("mc_status",),
            get_group=mc_dm.export_group_data,
            put_group=put_mc,
            get_global=mc_dm.export_global_data,
            put_global=mc_dm.import_global_data,
            list_groups=mc_dm.list_configured_groups,
        ),
        "mc_update": PluginAdapter(
            "xducraft_mc_update", "MC 版本订阅", False, ("mc_update",),
        ),
        "invite": PluginAdapter("xducraft_invite", "邀请码", True, ()),
        "features": PluginAdapter("xducraft_features", "QQ 功能管理", True, ()),
        "keyword": PluginAdapter(
            "xducraft_keyword", "关键词与入群欢迎", True, ("keyword_reply",),
            get_group=keyword_dm.export_scope_config,
            put_group=keyword_dm.replace_scope_config,
            get_global=lambda: keyword_dm.export_scope_config(None),
            put_global=lambda data: keyword_dm.replace_scope_config(None, data),
            list_groups=lambda: sorted(
                int(gid) for gid in keyword_dm.get_config()["groups"]
                if str(gid).isdigit() and int(gid) > 0
            ),
        ),
        "anti_recall": PluginAdapter(
            "xducraft_anti_recall", "反撤回", True, ("anti_recall",),
            get_global=anti_recall.get_config,
            put_global=anti_recall.update_config,
        ),
        "auto_friend": PluginAdapter(
            "xducraft_auto_friend", "自动好友申请", True, ("auto_accept_friend",),
        ),
        "happy_bot": PluginAdapter(
            "xducraft_happy_bot", "表情回应", True, ("emoji_reaction",),
            get_group=lambda gid: {
                "emoji_id": happy_dm.get_group_emoji_id(gid),
                "effective_emoji_id": happy_dm.get_emoji_id(gid),
            },
            put_group=put_happy,
            list_groups=happy_dm.list_configured_groups,
        ),
        "pig_bot": PluginAdapter(
            "xducraft_pig_bot", "猪猪图", True, ("pig_query", "pig_auto_push"),
            get_global=lambda: {"max_forward_results": pig.get_max_forward_results()},
            put_global=put_pig,
            list_groups=pig.list_configured_groups,
        ),
        "wordcloud": PluginAdapter(
            "xducraft_wordcloud", "词云", True, ("wordcloud",),
            get_global=wordcloud.load_config,
            put_global=wordcloud.update_global_config,
            list_groups=wordcloud.get_enabled_groups,
        ),
    }

    bots = {
        "20": SyntheticBot([
            {"group_id": GROUP_A, "group_name": "较大账号看到的名称"},
            {"group_id": GROUP_B, "group_name": "第二群"},
        ]),
        "10": SyntheticBot([
            {"group_id": GROUP_A, "group_name": "首选群名"},
        ]),
    }
    service = AdminService(
        adapters,
        feature_gate,
        deployment,
        lambda: bots,
        invite_store=invite,
        invite_settings=invite_settings,
    )
    service.deployment_context = DeploymentContext(
        {
            "mc_status": mc_settings_module,
            "invite": invite_settings_module,
            "auto_friend": friend_settings_module,
        },
        deployment,
    )

    clock = [1_800_000_000.25]
    auth = AdminAuth(PASSWORD, clock=lambda: clock[0])
    app = create_app(service, auth, tmp_path / "missing-dist")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield AdminEnvironment(
            app=app,
            client=client,
            service=service,
            auth=auth,
            clock=clock,
            bots=bots,
            feature_gate=feature_gate,
            happy_path=happy_path,
            pig=pig,
            wordcloud=wordcloud,
            anti_recall=anti_recall,
            invite=invite,
        )


@pytest.mark.asyncio
async def test_auth_boundary_unicode_cookie_csrf_logout_and_exact_expiry(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env

    anonymous = await env.client.get(f"/api/groups/{GROUP_A}/config/mc_status")
    assert anonymous.status_code == 401
    assert _error_code(anonymous) == "unauthenticated"

    static = await env.client.get("/")
    assert static.status_code == 503
    assert "npm ci" in static.text

    wrong_host = await env.client.get("/", headers={"Host": "attacker.example"})
    assert wrong_host.status_code == 403
    assert _error_code(wrong_host) == "invalid_host"

    remote_transport = httpx.ASGITransport(app=env.app, client=("192.0.2.10", 4567))
    async with httpx.AsyncClient(transport=remote_transport, base_url=BASE_URL) as remote:
        remote_response = await remote.get("/")
    assert remote_response.status_code == 403
    assert _error_code(remote_response) == "invalid_peer"

    malicious_login = await env.client.post(
        "/api/auth/login",
        json={"password": PASSWORD},
        headers={"Origin": "http://attacker.example"},
    )
    assert malicious_login.status_code == 403
    assert _error_code(malicious_login) == "invalid_origin"

    wrong_password = await _login(env, "错误口令")
    assert wrong_password.status_code == 401
    assert _error_code(wrong_password) == "invalid_password"

    login = await _login(env)
    assert login.status_code == 200
    session = login.json()
    assert session["authenticated"] is True
    assert isinstance(session["csrf_token"], str) and session["csrf_token"]
    assert session["expires_at"] == int(env.clock[0]) + SESSION_LIFETIME_SECONDS
    cookie = login.headers["set-cookie"]
    assert f"{COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie

    before = env.feature_gate.resolve("keyword_reply", GROUP_A)
    denied = await env.client.put(
        f"/api/groups/{GROUP_A}/features/keyword_reply",
        json={"enabled": False},
        headers={**ORIGIN_HEADERS, "If-Match": "0" * 64},
    )
    assert denied.status_code == 403
    assert _error_code(denied) == "invalid_csrf"
    assert env.feature_gate.resolve("keyword_reply", GROUP_A) == before

    denied_origin = await env.client.put(
        f"/api/groups/{GROUP_A}/features/keyword_reply",
        json={"enabled": False},
        headers={
            "Origin": "http://localhost:18765",
            "X-CSRF-Token": session["csrf_token"],
            "If-Match": "0" * 64,
        },
    )
    assert denied_origin.status_code == 403
    assert _error_code(denied_origin) == "invalid_origin"
    assert env.feature_gate.resolve("keyword_reply", GROUP_A) == before

    env.clock[0] = session["expires_at"] - 0.01
    live = await env.client.get("/api/auth/session")
    assert live.status_code == 200
    assert live.json()["authenticated"] is True

    session_cookie = env.client.cookies.get(COOKIE)
    env.clock[0] = session["expires_at"]
    expired = await env.client.get("/api/auth/session")
    assert expired.status_code == 401
    assert _error_code(expired) == "unauthenticated"

    env.clock[0] += 1
    relogin = await _login(env)
    csrf = relogin.json()["csrf_token"]
    old_cookie = env.client.cookies.get(COOKIE)
    logout = await env.client.post(
        "/api/auth/logout",
        headers=_write_headers(csrf),
    )
    assert logout.status_code == 204
    invalidated = await env.client.get(
        "/api/auth/session",
        cookies={COOKIE: old_cookie},
    )
    assert invalidated.status_code == 401
    assert session_cookie != old_cookie


@pytest.mark.asyncio
async def test_per_group_feature_isolation_qq_change_stale_revision_and_reset(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    login = await _login(env)
    csrf = login.json()["csrf_token"]

    group_a = await env.client.get(f"/api/groups/{GROUP_A}/features/keyword_reply")
    group_b = await env.client.get(f"/api/groups/{GROUP_B}/features/keyword_reply")
    assert group_a.status_code == group_b.status_code == 200
    assert group_a.json()["config"] == {"enabled": True}
    assert group_b.json()["config"] == {"enabled": True}
    assert group_a.json()["meta"]["source"] == "default"

    disabled = await env.client.put(
        f"/api/groups/{GROUP_A}/features/keyword_reply",
        json={"enabled": False},
        headers=_write_headers(csrf, group_a.json()["revision"]),
    )
    assert disabled.status_code == 200
    assert disabled.json()["config"] == {"enabled": False}
    assert env.feature_gate.is_enabled("keyword_reply", GROUP_A) is False
    assert env.feature_gate.is_enabled("keyword_reply", GROUP_B) is True

    # The QQ command side writes through the same feature gate while the page is open.
    env.feature_gate.set_enabled("keyword_reply", GROUP_A, True)
    stale = await env.client.put(
        f"/api/groups/{GROUP_A}/features/keyword_reply",
        json={"enabled": False},
        headers=_write_headers(csrf, disabled.json()["revision"]),
    )
    assert stale.status_code == 409
    assert _error_code(stale) == "stale_config"
    assert env.feature_gate.is_enabled("keyword_reply", GROUP_A) is True

    refreshed = await env.client.get(f"/api/groups/{GROUP_A}/features/keyword_reply")
    reset = await env.client.delete(
        f"/api/groups/{GROUP_A}/features/keyword_reply",
        headers=_write_headers(csrf, refreshed.json()["revision"]),
    )
    assert reset.status_code == 200
    assert reset.json()["config"] == {"enabled": True}
    assert reset.json()["meta"]["source"] == "default"

    global_resource = await env.client.get("/api/global/features/keyword_reply")
    changed_default = await env.client.put(
        "/api/global/features/keyword_reply",
        json={"enabled": False},
        headers=_write_headers(csrf, global_resource.json()["revision"]),
    )
    assert changed_default.status_code == 200
    assert env.feature_gate.resolve("keyword_reply", GROUP_A) == (False, "default")
    assert env.feature_gate.resolve("keyword_reply", GROUP_B) == (False, "default")


@pytest.mark.asyncio
async def test_happy_group_only_a_b_root_and_persistence(admin_env: AdminEnvironment) -> None:
    env = admin_env
    happy_dm.set_emoji_id("123", group_id=GROUP_A)
    happy_dm.set_emoji_id("456", group_id=GROUP_B)
    login = await _login(env)
    csrf = login.json()["csrf_token"]

    current = await env.client.get(f"/api/groups/{GROUP_A}/config/happy_bot")
    assert current.status_code == 200
    assert current.json()["config"] == {"emoji_id": "123"}
    assert current.json()["meta"]["effective_emoji_id"] == "123"

    saved = await env.client.put(
        f"/api/groups/{GROUP_A}/config/happy_bot",
        json={"emoji_id": "789"},
        headers=_write_headers(csrf, current.json()["revision"]),
    )
    assert saved.status_code == 200
    assert happy_dm.get_emoji_id(GROUP_A) == "789"
    assert happy_dm.get_emoji_id(GROUP_B) == "456"
    assert happy_dm.get_emoji_id() == "111"

    # A fresh JsonStore instance exercises the persisted group schema, not a cache.
    happy_dm._store = JsonStore(
        str(env.happy_path), happy_dm._default_data, happy_dm._normalize,
    )
    assert happy_dm.get_group_emoji_id(GROUP_A) == "789"
    assert happy_dm.get_group_emoji_id(GROUP_B) == "456"
    assert happy_dm.get_emoji_id() == "111"

    fresh = await env.client.get(f"/api/groups/{GROUP_A}/config/happy_bot")
    cleared = await env.client.put(
        f"/api/groups/{GROUP_A}/config/happy_bot",
        json={"emoji_id": None},
        headers=_write_headers(csrf, fresh.json()["revision"]),
    )
    assert cleared.status_code == 200
    assert cleared.json()["config"] == {"emoji_id": None}
    assert cleared.json()["meta"]["effective_emoji_id"] == "111"
    assert happy_dm.get_group_emoji_id(GROUP_A) is None
    assert happy_dm.get_group_emoji_id(GROUP_B) == "456"
    assert happy_dm.get_emoji_id() == "111"

    global_get = await env.client.get("/api/global/config/happy_bot")
    global_put = await env.client.put(
        "/api/global/config/happy_bot",
        json={"emoji_id": "999"},
        headers=_write_headers(csrf, "0" * 64),
    )
    assert global_get.status_code == global_put.status_code == 404
    assert _error_code(global_get) == _error_code(global_put) == "unknown_resource"
    assert happy_dm.get_emoji_id() == "111"


@pytest.mark.asyncio
async def test_mc_full_tree_roundtrip_and_invalid_payloads_are_non_mutating(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    csrf = (await _login(env)).json()["csrf_token"]
    resource = await env.client.get(f"/api/groups/{GROUP_A}/config/mc_status")

    server = {
        "ip": "play.example.com:25565",
        "comment": "主服",
        "tag": "生存",
        "tag_color": "a1b2c3",
        "ignore_in_list": False,
        "hide_ip": True,
        "display_name": "校园线路",
        "auth_mode": "xdu",
        "priority": -7,
        "children": [{
            "ip": "child.example.com",
            "comment": "子服",
            "tag": "创造",
            "tag_color": "00ff7f",
            "ignore_in_list": True,
            "hide_ip": False,
            "display_name": "保留旧显示字段",
            "auth_mode": "offline",
            "priority": 4,
            "children": [],
        }],
    }
    payload = {
        "servers": [server],
        "footer": "页脚",
        "show_offline_by_default": True,
        "status_api_source": "custom",
        "status_api_url": "https://status.example.test/query",
        "default_auth_mode": "mixed",
        "auth_detect": True,
        "quiet_admin_replies": False,
    }
    saved = await env.client.put(
        f"/api/groups/{GROUP_A}/config/mc_status",
        json=payload,
        headers=_write_headers(csrf, resource.json()["revision"]),
    )
    assert saved.status_code == 200
    expected = copy.deepcopy(payload)
    expected["servers"][0]["tag_color"] = "A1B2C3"
    expected["servers"][0]["children"][0]["tag_color"] = "00FF7F"
    assert saved.json()["config"] == expected
    assert mc_dm.export_group_data(GROUP_A) == expected
    assert mc_dm.export_group_data(GROUP_B)["servers"] == []

    persisted = copy.deepcopy(mc_dm.export_group_data(GROUP_A))

    duplicate = copy.deepcopy(expected)
    duplicate["servers"].append(copy.deepcopy(duplicate["servers"][0]))
    duplicate_response = await env.client.put(
        f"/api/groups/{GROUP_A}/config/mc_status",
        json=duplicate,
        headers=_write_headers(csrf, saved.json()["revision"]),
    )
    assert duplicate_response.status_code == 422
    assert mc_dm.export_group_data(GROUP_A) == persisted

    invalid_url = copy.deepcopy(expected)
    invalid_url["status_api_url"] = "file:///etc/passwd"
    invalid_url_response = await env.client.put(
        f"/api/groups/{GROUP_A}/config/mc_status",
        json=invalid_url,
        headers=_write_headers(csrf, saved.json()["revision"]),
    )
    assert invalid_url_response.status_code == 422
    assert mc_dm.export_group_data(GROUP_A) == persisted

    node: dict[str, Any] | None = None
    for level in reversed(range(14)):
        node = {
            "ip": f"level-{level}.example.test",
            "comment": "",
            "tag": "",
            "tag_color": "",
            "ignore_in_list": False,
            "hide_ip": False,
            "display_name": "",
            "auth_mode": "",
            "priority": None,
            "children": [] if node is None else [node],
        }
    too_deep = copy.deepcopy(expected)
    too_deep["servers"] = [node]
    deep_response = await env.client.put(
        f"/api/groups/{GROUP_A}/config/mc_status",
        json=too_deep,
        headers=_write_headers(csrf, saved.json()["revision"]),
    )
    assert deep_response.status_code == 422
    assert mc_dm.export_group_data(GROUP_A) == persisted


@pytest.mark.asyncio
async def test_keyword_real_media_cq_text_and_opaque_roundtrip(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    csrf = (await _login(env)).json()["csrf_token"]
    image = _png_bytes()

    uploaded = await env.client.post(
        "/api/keyword/media",
        content=image,
        headers={
            **_write_headers(csrf),
            "Content-Type": "image/png",
        },
    )
    assert uploaded.status_code == 200
    name = uploaded.json()["name"]
    assert len(name) == 36 and name.endswith(".img")

    resource = await env.client.get(f"/api/groups/{GROUP_A}/config/keyword")
    payload = {
        "rules": [{
            "id": None,
            "keywords": ["面板测试"],
            "match": "exact",
            "enabled": True,
            "cooldown": 0,
            "replies": [[
                {"type": "text", "text": "[CQ:at,qq=all]"},
                {"type": "image", "name": name},
                {"type": "face", "id": "123"},
                {"type": "at", "qq": "10086"},
            ]],
        }],
        "join_replies": [[{"type": "text", "text": "欢迎加入"}]],
        "default_cooldown": None,
    }
    saved = await env.client.put(
        f"/api/groups/{GROUP_A}/config/keyword",
        json=payload,
        headers=_write_headers(csrf, resource.json()["revision"]),
    )
    assert saved.status_code == 200
    rule_id = saved.json()["config"]["rules"][0]["id"]
    assert isinstance(rule_id, str) and rule_id

    matched = keyword_dm.match_rules("面板测试", GROUP_A)
    assert matched is not None
    from nonebot.adapters.onebot.v11 import Message

    message = Message(matched["replies"][0])
    assert [segment.type for segment in message] == ["text", "image", "face", "at"]
    assert message[0].data["text"] == "[CQ:at,qq=all]"
    assert message[1].data["file"] == f"kwlocal://{name}"
    assert message[2].data["id"] == "123"
    assert message[3].data["qq"] == "10086"
    restored = restore_reply(matched["replies"][0])
    assert "file:///" in restored and name in restored

    media = await env.client.get(f"/api/keyword/media/{name}")
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/png")
    assert media.content == image

    unauthenticated_transport = httpx.ASGITransport(
        app=env.app, client=("127.0.0.1", 10000),
    )
    async with httpx.AsyncClient(
        transport=unauthenticated_transport, base_url=BASE_URL,
    ) as anonymous:
        anonymous_media = await anonymous.get(f"/api/keyword/media/{name}")
    assert anonymous_media.status_code == 401

    invalid_image = await env.client.post(
        "/api/keyword/media",
        content=b"<svg>not an image</svg>",
        headers={**_write_headers(csrf), "Content-Type": "image/png"},
    )
    assert invalid_image.status_code == 415
    too_large = await env.client.post(
        "/api/keyword/media",
        content=b"x" * (10 * 1024 * 1024 + 1),
        headers={**_write_headers(csrf), "Content-Type": "image/png"},
    )
    assert too_large.status_code == 413
    traversal = await env.client.get("/api/keyword/media/..not-an-image.img")
    assert traversal.status_code == 404

    original_reply = matched["replies"][0] + "[CQ:record,file=voice.amr]"
    assert keyword_dm.update_rule(rule_id, GROUP_A, replies=[original_reply]) is True
    with_opaque = await env.client.get(f"/api/groups/{GROUP_A}/config/keyword")
    opaque_config = with_opaque.json()["config"]
    opaque = next(
        segment
        for segment in opaque_config["rules"][0]["replies"][0]
        if segment["type"] == "opaque"
    )
    opaque_config["rules"][0]["replies"][0].remove(opaque)
    opaque_config["rules"][0]["replies"][0].insert(0, opaque)
    opaque_saved = await env.client.put(
        f"/api/groups/{GROUP_A}/config/keyword",
        json=opaque_config,
        headers=_write_headers(csrf, with_opaque.json()["revision"]),
    )
    assert opaque_saved.status_code == 200
    stored_after_opaque = keyword_dm.find_rule(rule_id, GROUP_A)
    assert stored_after_opaque is not None
    assert "[CQ:record,file=voice.amr]" in stored_after_opaque["replies"][0]

    forged = copy.deepcopy(opaque_saved.json()["config"])
    forged["rules"].append({
        "id": None,
        "keywords": ["伪造引用"],
        "match": "exact",
        "enabled": True,
        "cooldown": 0,
        "replies": [[copy.deepcopy(opaque)]],
    })
    rejected = await env.client.put(
        f"/api/groups/{GROUP_A}/config/keyword",
        json=forged,
        headers=_write_headers(csrf, opaque_saved.json()["revision"]),
    )
    assert rejected.status_code == 422
    assert _error_code(rejected) == "invalid_config"
    assert keyword_dm.find_rule("伪造引用", GROUP_A) is None


@pytest.mark.asyncio
async def test_pig_wordcloud_and_anti_recall_use_actual_temporary_stores(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    csrf = (await _login(env)).json()["csrf_token"]

    # Merely rendering the cards invokes Pig's getter and must not create a group.
    assert env.pig.list_configured_groups() == []
    cards = await env.client.get("/api/groups/99999/plugins")
    assert cards.status_code == 200
    assert env.pig.list_configured_groups() == []

    pig_resource = await env.client.get("/api/global/config/pig_bot")
    pig_saved = await env.client.put(
        "/api/global/config/pig_bot",
        json={"max_forward_results": 12},
        headers=_write_headers(csrf, pig_resource.json()["revision"]),
    )
    assert pig_saved.status_code == 200
    assert env.pig.get_max_forward_results() == 12

    env.wordcloud.set_group_enabled(GROUP_A, True)
    env.wordcloud.set_group_enabled(GROUP_B, True)
    wordcloud_resource = await env.client.get("/api/global/config/wordcloud")
    wordcloud_payload = {
        "ban_user_ids": ["10086", "10086", "10010"],
        "min_word_length": 3,
        "max_words": 320,
        "retention_days": 365,
        "additional_stopwords": ["  HELLO ", "hello", "World"],
        "footer_subtitle": "测试副标题",
        "footer_branding_enabled": False,
        "footer_branding_text": "Local Panel",
    }
    wordcloud_saved = await env.client.put(
        "/api/global/config/wordcloud",
        json=wordcloud_payload,
        headers=_write_headers(csrf, wordcloud_resource.json()["revision"]),
    )
    assert wordcloud_saved.status_code == 200
    assert env.wordcloud.get_enabled_groups() == [GROUP_A, GROUP_B]
    assert env.wordcloud.get_ban_user_ids() == [10086, 10010]
    assert env.wordcloud.get_wordcloud_options() == {
        "min_word_length": 3,
        "max_words": 320,
    }
    assert env.wordcloud.load_config()["additional_stopwords"] == ["hello", "world"]
    env.wordcloud.set_user_banned(10000, True)
    refreshed_wordcloud = await env.client.get("/api/global/config/wordcloud")
    assert refreshed_wordcloud.json()["config"]["ban_user_ids"] == [
        "10086", "10010", "10000",
    ]

    anti_resource = await env.client.get("/api/global/config/anti_recall")
    anti_payload = {
        "cache_retention_hours": 72,
        "recall_retention_days": 30,
        "max_query_results": 55,
        "save_media": False,
        "max_media_mb": 40,
        "include_self": True,
        "exempt_user_ids": ["20002", "20002", "20003"],
    }
    anti_saved = await env.client.put(
        "/api/global/config/anti_recall",
        json=anti_payload,
        headers=_write_headers(csrf, anti_resource.json()["revision"]),
    )
    assert anti_saved.status_code == 200
    assert env.anti_recall.get_config() == {
        **anti_payload,
        "exempt_user_ids": [20002, 20003],
    }
    assert env.anti_recall.is_user_exempt(20002) is True


@pytest.mark.asyncio
async def test_invite_initialization_deployment_lock_and_secret_never_leaks(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    csrf = (await _login(env)).json()["csrf_token"]

    resource = await env.client.get(f"/api/groups/{GROUP_A}/invite")
    assert resource.status_code == 200
    assert resource.json()["meta"]["initialized"] is False
    premature = await env.client.put(
        f"/api/groups/{GROUP_A}/invite",
        json={"enabled": True},
        headers=_write_headers(csrf, resource.json()["revision"]),
    )
    assert premature.status_code == 409
    assert _error_code(premature) == "invite_not_initialized"
    assert env.invite.get_state().self_service_enabled is False

    wrong_group = await env.client.get(f"/api/groups/{GROUP_B}/invite")
    assert wrong_group.status_code == 409
    assert _error_code(wrong_group) == "invite_group_not_bound"

    assert env.invite.initialize([90001], initialized_at=123456, initialized_by=90000)
    initialized = await env.client.get(f"/api/groups/{GROUP_A}/invite")
    disabled = await env.client.put(
        f"/api/groups/{GROUP_A}/invite",
        json={"enabled": False},
        headers=_write_headers(csrf, initialized.json()["revision"]),
    )
    assert disabled.status_code == 200
    assert env.invite.get_state().self_service_enabled is False

    deployment_resource = await env.client.get("/api/deployment")
    deployment_text = deployment_resource.text
    assert "active-secret-do-not-disclose" not in deployment_text
    assert deployment_resource.json()["meta"]["active"]["invite_api_secret_configured"] is True

    locked = await env.client.put(
        "/api/deployment",
        json={"set": {"invite_group_id": str(GROUP_B)}, "unset": []},
        headers=_write_headers(csrf, deployment_resource.json()["revision"]),
    )
    assert locked.status_code == 409
    assert _error_code(locked) == "invite_group_locked"

    replacement_secret = "replacement-secret-must-never-appear"
    secret_saved = await env.client.put(
        "/api/deployment",
        json={"set": {"invite_api_secret": replacement_secret}, "unset": []},
        headers=_write_headers(csrf, deployment_resource.json()["revision"]),
    )
    assert secret_saved.status_code == 200
    assert replacement_secret not in secret_saved.text
    assert "active-secret-do-not-disclose" not in secret_saved.text
    secret_body = secret_saved.json()
    assert secret_body["config"]["pending"]["invite_api_secret_configured"] is True
    assert secret_body["meta"]["active"]["invite_api_secret_configured"] is True
    assert secret_body["meta"]["restart_required"] is True
    assert "invite_api_secret" in secret_body["meta"]["changed_keys"]
    assert deployment.read_overrides()["invite_api_secret"] == replacement_secret

    invalid = await env.client.put(
        "/api/deployment",
        json={
            "set": {
                "invite_api_secret": "another-secret-never-echo",
                "mcs_width": 1,
            },
            "unset": [],
        },
        headers=_write_headers(csrf, secret_body["revision"]),
    )
    assert invalid.status_code == 422
    assert "another-secret-never-echo" not in invalid.text
    assert replacement_secret not in invalid.text
    assert deployment.read_overrides()["invite_api_secret"] == replacement_secret


@pytest.mark.asyncio
async def test_group_cache_keeps_last_success_and_marks_only_cached_rows_stale(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    csrf = (await _login(env)).json()["csrf_token"]

    # Add a configuration-only group that no connected bot reports.
    happy_resource = await env.client.get(
        f"/api/groups/{CONFIG_ONLY_GROUP}/config/happy_bot",
    )
    configured = await env.client.put(
        f"/api/groups/{CONFIG_ONLY_GROUP}/config/happy_bot",
        json={"emoji_id": "333"},
        headers=_write_headers(csrf, happy_resource.json()["revision"]),
    )
    assert configured.status_code == 200

    online = await env.client.get("/api/groups")
    assert online.status_code == 200
    by_id = {row["group_id"]: row for row in online.json()["groups"]}
    assert by_id[str(GROUP_A)] == {
        "group_id": str(GROUP_A),
        "name": "首选群名",
        "bot_ids": ["10", "20"],
        "connected": True,
        "stale": False,
    }
    assert by_id[str(CONFIG_ONLY_GROUP)] == {
        "group_id": str(CONFIG_ONLY_GROUP),
        "name": f"群 {CONFIG_ONLY_GROUP}",
        "bot_ids": [],
        "connected": False,
        "stale": False,
    }

    for bot in env.bots.values():
        bot.fail = True
    offline = await env.client.get("/api/groups")
    assert offline.status_code == 200
    offline_by_id = {row["group_id"]: row for row in offline.json()["groups"]}
    assert offline_by_id[str(GROUP_A)]["name"] == "首选群名"
    assert offline_by_id[str(GROUP_A)]["bot_ids"] == ["10", "20"]
    assert offline_by_id[str(GROUP_A)]["connected"] is False
    assert offline_by_id[str(GROUP_A)]["stale"] is True
    assert offline_by_id[str(CONFIG_ONLY_GROUP)]["connected"] is False
    assert offline_by_id[str(CONFIG_ONLY_GROUP)]["stale"] is False
    assert len(offline.json()["warnings"]) == 2


@pytest.mark.asyncio
async def test_embedded_server_real_loopback_socket_bind_failure_and_release(
    admin_env: AdminEnvironment,
) -> None:
    env = admin_env
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()

    previous_sigint = signal.getsignal(signal.SIGINT)
    holder = AdminServer()
    await holder.start(env.app, port)
    try:
        assert holder.running is True
        assert holder._socket is not None
        assert holder._socket.getsockname()[0] == "127.0.0.1"
        assert signal.getsignal(signal.SIGINT) is previous_sigint
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", timeout=2.0,
        ) as network_client:
            response = await network_client.get("/")
        assert response.status_code == 503
        assert response.headers["x-content-type-options"] == "nosniff"
    finally:
        await holder.stop()

    assert holder.running is False
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    try:
        failed_holder = AdminServer()
        with pytest.raises(AdminServerError) as caught:
            await failed_holder.start(env.app, port)
        assert caught.value.code == "web_admin_bind_failed"
        await asyncio.sleep(0)
        assert asyncio.get_running_loop().is_running()
    finally:
        blocker.close()


@pytest.mark.asyncio
async def test_qq_invite_init_rechecks_pending_binding_after_member_lookup(admin_env, monkeypatch):
    from xducraft_bot.plugins import xducraft_invite as invite_plugin

    class Finished(Exception):
        pass

    async def finish(*args, **kwargs):
        raise Finished()

    async def owner(*args):
        return True

    async def members(**kwargs):
        # A web write happens while the QQ initialization awaits OneBot.
        deployment.update_overrides({"invite_group_id": GROUP_B}, [])
        return [{"user_id": 12345}]

    monkeypatch.setattr(invite_plugin, "store", admin_env.invite)
    monkeypatch.setattr(invite_plugin, "SETTINGS", admin_env.service.invite_settings)
    monkeypatch.setattr(invite_plugin, "is_superuser", owner)
    monkeypatch.setattr(invite_plugin.admin_command, "finish", finish)
    with pytest.raises(Finished):
        await invite_plugin._handle_init(
            SimpleNamespace(get_group_member_list=members), SimpleNamespace(user_id=12345),
        )
    assert not admin_env.invite.get_state().initialized
    assert deployment.read_overrides()["invite_group_id"] == GROUP_B


@pytest.mark.asyncio
async def test_server_shutdown_closes_an_incomplete_request(admin_env):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    holder = AdminServer()
    await holder.start(admin_env.app, port)
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        body = b'{"password":"'
        writer.write((
            f"POST /api/auth/login HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"Origin: http://127.0.0.1:{port}\r\n"
            "Content-Type: application/json\r\n"
            "Transfer-Encoding: chunked\r\n\r\n"
        ).encode() + f"{len(body):x}\r\n".encode() + body + b"\r\n")
        await writer.drain()
        await asyncio.sleep(0.05)
        await asyncio.wait_for(holder.stop(), timeout=5.5)
        response = await asyncio.wait_for(reader.read(), timeout=2)
        assert b'"authenticated":true' not in response
        assert b"Set-Cookie: xducraft_admin_session" not in response
        reopened = socket.socket()
        try:
            reopened.bind(("127.0.0.1", port))
        finally:
            reopened.close()
    finally:
        writer.close()
        await writer.wait_closed()
        await holder.stop()


@pytest.mark.asyncio
async def test_group_avatar_authentication_validation_and_success_cache(
    admin_env: AdminEnvironment, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    requests: list[str] = []
    image = _png_bytes()

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, content=image, headers={"Content-Type": "text/plain"})

    monkeypatch.setattr(
        "xducraft_bot.admin.app.GroupAvatarCache",
        lambda: GroupAvatarCache(transport=httpx.MockTransport(upstream)),
    )
    app = create_app(admin_env.service, admin_env.auth, tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        assert (await client.get(f"/api/groups/{GROUP_A}/avatar")).status_code == 401
        assert requests == []
        assert (await client.post(
            "/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN_HEADERS,
        )).status_code == 200
        assert (await client.get("/api/groups/0/avatar")).status_code == 422
        assert requests == []
        response = await client.get(f"/api/groups/{GROUP_A}/avatar")
        assert response.status_code == 200
        assert response.content == image
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get(f"/api/groups/{GROUP_A}/avatar")).content == image
        assert requests == [f"https://p.qlogo.cn/gh/{GROUP_A}/{GROUP_A}/100"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["redirect", "oversize", "nonimage"])
async def test_group_avatar_rejects_unsafe_upstream_without_leaking_details(
    admin_env: AdminEnvironment, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str,
) -> None:
    requests: list[str] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://secret.example/private"})
        if failure == "oversize":
            return httpx.Response(
                200, content=b"x" * (AVATAR_MAX_BYTES + 1),
                headers={"Content-Length": "1", "Content-Type": "image/png"},
            )
        return httpx.Response(200, content=b"<svg>private upstream details</svg>")

    monkeypatch.setattr(
        "xducraft_bot.admin.app.GroupAvatarCache",
        lambda: GroupAvatarCache(transport=httpx.MockTransport(upstream)),
    )
    app = create_app(admin_env.service, admin_env.auth, tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        assert (await client.post(
            "/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN_HEADERS,
        )).status_code == 200
        for _ in range(2):
            response = await client.get(f"/api/groups/{GROUP_A}/avatar")
            assert response.status_code == 502
            assert response.json()["error"]["code"] == "avatar_unavailable"
            assert "secret.example" not in response.text
            assert "private" not in response.text
        assert requests == [f"https://p.qlogo.cn/gh/{GROUP_A}/{GROUP_A}/100"] * 2
