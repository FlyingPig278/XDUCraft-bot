from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import httpx
import pytest
from pydantic import Field, SecretStr, StrictInt, StrictStr, field_validator

from xducraft_admin.adapters import discover_catalog
from xducraft_admin.app import COOKIE, create_app
from xducraft_admin.auth import AdminAuth
from xducraft_admin.service import AdminService
from xducraft_bot.shared import configuration
from xducraft_bot.shared.configuration import (
    ConfigContext,
    ConfigModel,
    ConfigResource,
    ConfigSnapshot,
    PluginConfiguration,
    PROTOCOL_KEY,
    StartupConfig,
)

GROUP_A = 10001
GROUP_B = 10002
CONTROL_ONLY_GROUP = 30003
PASSWORD = "管理员-十二字符口令-安全"
BASE_URL = "http://127.0.0.1:18765"
ORIGIN = {"Origin": BASE_URL}


class Credential(ConfigModel):
    username: StrictStr = ""
    password: SecretStr = Field(
        SecretStr(""),
        json_schema_extra={"writeOnly": True, "x-ui-secret": True},
    )


class Endpoint(ConfigModel):
    name: StrictStr
    credential: Credential


class CustomConfig(ConfigModel):
    title: StrictStr = "Default"
    api_key: SecretStr = Field(
        SecretStr(""),
        json_schema_extra={"writeOnly": True, "x-ui-secret": True},
    )
    credential: Credential = Field(default_factory=Credential)
    endpoints: list[Endpoint] = Field(
        default_factory=list,
        json_schema_extra={"x-ui-label-field": "name"},
    )
    positional_credentials: list[Credential] = Field(default_factory=list)
    optional_token: Optional[SecretStr] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()


class ChangedCustomConfig(CustomConfig):
    required_limit: StrictInt


class StartupModel(ConfigModel):
    listen_port: StrictInt = 8765
    startup_token: SecretStr = Field(
        SecretStr(""),
        json_schema_extra={"writeOnly": True, "x-ui-secret": True},
    )


class NativeModel(ConfigModel):
    value: StrictInt = 1


class ScopedNativeModel(ConfigModel):
    value: StrictInt = 1
    shared_token: SecretStr = Field(
        SecretStr("scope-secret-marker"),
        json_schema_extra={"x-ui-scope": "global_only", "writeOnly": True},
    )


class SyntheticBot:
    def __init__(self, nickname: str = "测试机器人") -> None:
        self.fail = False
        self.login_fail = False
        self.nickname = nickname

    async def get_login_info(self):
        if self.login_fail:
            raise RuntimeError("offline")
        return {"user_id": 999999, "nickname": self.nickname}

    async def get_group_list(self):
        if self.fail:
            raise RuntimeError("offline")
        return [{"group_id": GROUP_A, "group_name": "测试群"}]


class MemoryMedia:
    max_bytes = 32
    mime_types = ("image/png",)

    def __init__(self, root: Path):
        self.root = root

    def upload(self, content: bytes) -> str:
        if not content.startswith(b"PNG"):
            raise ValueError("invalid")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "asset.img"
        path.write_bytes(content)
        return path.name

    def resolve(self, name: str):
        if name != "asset.img" or not (self.root / name).is_file():
            raise FileNotFoundError(name)
        return self.root / name, "image/png"


class MemoryStartup:
    def __init__(self) -> None:
        self.values = {"listen_port": 8765, "startup_token": "startup-secret"}
        self.active = copy.deepcopy(self.values)

    def read(self, declaration):
        return ConfigSnapshot(
            copy.deepcopy(self.values),
            {
                "active": copy.deepcopy(self.active),
                "defaults": {"listen_port": 8765, "startup_token": "base-secret"},
                "overridden": ["startup_token"],
                "restart_required": self.values != self.active,
            },
            {"stored": copy.deepcopy(self.values), "active": copy.deepcopy(self.active)},
        )

    def write(self, declaration, patch):
        self.values.update(patch["set"])
        for key in patch["unset"]:
            self.values[key] = {"listen_port": 8765, "startup_token": "base-secret"}[key]
        return self.read(declaration)


class MemoryStore:
    def __init__(self) -> None:
        base = {
            "title": "Global",
            "api_key": "global-secret",
            "credential": {"username": "root", "password": "nested-secret"},
            "endpoints": [
                {"name": "first", "credential": {"username": "a", "password": "first-secret"}},
                {"name": "second", "credential": {"username": "b", "password": "second-secret"}},
            ],
            "positional_credentials": [
                {"username": "position-a", "password": "position-secret-a"},
                {"username": "position-b", "password": "position-secret-b"},
            ],
            "optional_token": "optional-secret",
        }
        self.global_value = base
        self.groups = {GROUP_A: {**copy.deepcopy(base), "title": "Group A"}}

    def read(self, context: ConfigContext) -> ConfigSnapshot:
        values = self.global_value if context.group_id is None else self.groups.get(context.group_id, configuration.private_json(CustomConfig()))
        values = copy.deepcopy(values)
        return ConfigSnapshot(
            values,
            {
                "defaults": copy.deepcopy(self.global_value),
                "effective": copy.deepcopy(values),
                "applied": copy.deepcopy(values),
            },
            {"group_id": context.group_id, "values": values},
        )

    def write(self, context: ConfigContext, values: dict[str, Any]) -> None:
        if context.check_current is not None:
            context.check_current(self.read(context))
        if context.group_id is None:
            self.global_value = copy.deepcopy(values)
        else:
            self.groups[context.group_id] = copy.deepcopy(values)

    def list_groups(self):
        return sorted(self.groups)


class FakePlugin:
    def __init__(self, plugin_id: str, name: str, declaration=None):
        self.id_ = plugin_id
        self.metadata = SimpleNamespace(
            name=name,
            description=name + " description",
            extra={PROTOCOL_KEY: declaration} if declaration is not None else {},
        )


class Environment:
    def __init__(self, app, client, service, store, startup, feature_gate):
        self.app = app
        self.client = client
        self.service = service
        self.store = store
        self.startup = startup
        self.feature_gate = feature_gate


@pytest.fixture
async def environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_feature_gate,
) -> Environment:
    feature_gate = isolated_feature_gate
    feature_gate.register(feature_gate.Feature("custom_feature", "自定义功能"))
    store = MemoryStore()
    startup = MemoryStartup()
    store.blocked_groups = set()
    media = MemoryMedia(tmp_path / "media")
    declaration = PluginConfiguration(
        key="custom",
        name="动态自定义插件",
        resources={
            "global": ConfigResource(CustomConfig, store.read, store.write),
            "group": ConfigResource(CustomConfig, store.read, store.write),
        },
        feature_keys=("custom_feature",),
        list_groups=store.list_groups,
        status=lambda context: {"feature_effective": {"custom_feature": context.group_id not in store.blocked_groups}},
        startup=StartupConfig(
            StartupModel,
            active=lambda: copy.deepcopy(startup.active),
            base=lambda: {"listen_port": 8765, "startup_token": "base-secret"},
            normalize=lambda value: value,
        ),
        media=lambda: media,
    )
    monkeypatch.setitem(configuration._registry, declaration.key, declaration)
    configuration.set_plugin_enabled("custom", True, actor="test")
    feature_gate.set_enabled("custom_feature", GROUP_A, True)
    plugins = [
        FakePlugin("third_party_plain", "未声明插件"),
        FakePlugin("xducraft_custom", "动态自定义插件", declaration),
    ]
    catalog = lambda: discover_catalog(plugins)
    bot = SyntheticBot()
    service = AdminService(catalog, feature_gate, SimpleNamespace(), lambda: {"10": bot}, startup=startup)
    auth = AdminAuth(PASSWORD)
    app = create_app(service, auth, tmp_path / "missing-dist")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield Environment(app, client, service, store, startup, feature_gate)


async def login(env: Environment):
    response = await env.client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert response.status_code == 200
    return response.json()["csrf_token"]


def headers(csrf: str, revision: Optional[str] = None):
    result = {**ORIGIN, "X-CSRF-Token": csrf}
    if revision is not None:
        result["If-Match"] = revision
    return result


def code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


@pytest.mark.asyncio
async def test_auth_security_boundary_and_static_fallback(environment: Environment):
    env = environment
    assert (await env.client.get("/api/plugins")).status_code == 401
    assert (await env.client.get("/")).status_code == 503
    assert (await env.client.get("/", headers={"Host": "attacker.example"})).status_code == 403
    bad = await env.client.post("/api/auth/login", json={"password": "wrong-password"}, headers=ORIGIN)
    assert bad.status_code == 401

    csrf = await login(env)
    cookie = env.client.cookies.get(COOKIE)
    assert cookie
    denied = await env.client.put(
        "/api/global/config/custom",
        json={},
        headers={**ORIGIN, "If-Match": "0" * 64},
    )
    assert denied.status_code == 403
    assert code(denied) == "invalid_csrf"

    logout = await env.client.post("/api/auth/logout", headers=headers(csrf))
    assert logout.status_code == 204
    assert (await env.client.get("/api/plugins")).status_code == 401


@pytest.mark.asyncio
async def test_undeclared_plugin_cannot_acquire_full_disable_control(environment: Environment):
    env = environment
    csrf = await login(env)
    control = await env.client.get("/api/plugins/third_party_plain/enabled")
    assert control.status_code == 404
    denied = await env.client.put(
        "/api/plugins/third_party_plain/enabled",
        json={"enabled": True},
        headers=headers(csrf, "0" * 64),
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_generic_replace_normalization_group_isolation_and_stale_qq_write(environment: Environment):
    env = environment
    csrf = await login(env)
    response = await env.client.get(f"/api/groups/{GROUP_A}/config/custom")
    resource = response.json()
    draft = resource["config"]
    draft["title"] = "  Normalized  "
    saved = await env.client.put(
        f"/api/groups/{GROUP_A}/config/custom",
        json=draft,
        headers=headers(csrf, resource["revision"]),
    )
    assert saved.status_code == 200
    assert saved.json()["config"]["title"] == "Normalized"
    assert env.store.groups[GROUP_A]["title"] == "Normalized"
    assert GROUP_B not in env.store.groups
    assert env.store.global_value["title"] == "Global"

    stale = (await env.client.get(f"/api/groups/{GROUP_A}/config/custom")).json()
    env.store.groups[GROUP_A]["title"] = "QQ changed"
    stale["config"]["title"] = "browser overwrite"
    rejected = await env.client.put(
        f"/api/groups/{GROUP_A}/config/custom",
        json=stale["config"],
        headers=headers(csrf, stale["revision"]),
    )
    assert rejected.status_code == 409
    assert code(rejected) == "stale_config"
    assert env.store.groups[GROUP_A]["title"] == "QQ changed"

    schema_draft = (await env.client.get(f"/api/groups/{GROUP_A}/config/custom")).json()
    declaration = env.service.catalog()["custom"].declaration
    assert declaration is not None
    declaration.resources["group"] = ConfigResource(
        ChangedCustomConfig,
        env.store.read,
        env.store.write,
    )
    schema_draft["config"]["title"] = "schema-stale"
    schema_stale = await env.client.put(
        f"/api/groups/{GROUP_A}/config/custom",
        json=schema_draft["config"],
        headers=headers(csrf, schema_draft["revision"]),
    )
    assert schema_stale.status_code == 409
    assert code(schema_stale) == "stale_config"


@pytest.mark.asyncio
async def test_recursive_secret_redaction_preservation_and_safe_arrays(environment: Environment):
    env = environment
    csrf = await login(env)
    response = await env.client.get("/api/global/config/custom")
    resource = response.json()
    serialized = response.text
    for secret in (
        "global-secret", "nested-secret", "first-secret", "second-secret",
        "position-secret-a", "position-secret-b", "optional-secret",
    ):
        assert secret not in serialized
    assert "api_key" not in resource["config"]
    assert "password" not in resource["config"]["credential"]
    assert resource["meta"]["secret_fields"] == {
        "api_key": True,
        "credential.password": True,
        "endpoints.0.credential.password": True,
        "endpoints.1.credential.password": True,
        "positional_credentials.0.password": True,
        "positional_credentials.1.password": True,
        "optional_token": True,
    }

    resource["config"]["title"] = "Kept secrets"
    saved = await env.client.put(
        "/api/global/config/custom",
        json=resource["config"],
        headers=headers(csrf, resource["revision"]),
    )
    assert saved.status_code == 200
    assert env.store.global_value["api_key"] == "global-secret"
    assert env.store.global_value["credential"]["password"] == "nested-secret"
    assert env.store.global_value["optional_token"] == "optional-secret"
    assert [item["credential"]["password"] for item in env.store.global_value["endpoints"]] == ["first-secret", "second-secret"]

    current = (await env.client.get("/api/global/config/custom")).json()
    current["config"]["endpoints"].reverse()
    # x-ui-label-field supplies stable identity, so omitted secrets follow their item.
    moved = await env.client.put(
        "/api/global/config/custom",
        json=current["config"],
        headers=headers(csrf, current["revision"]),
    )
    assert moved.status_code == 200
    assert [item["name"] for item in env.store.global_value["endpoints"]] == ["second", "first"]
    assert [item["credential"]["password"] for item in env.store.global_value["endpoints"]] == ["second-secret", "first-secret"]

    positional = (await env.client.get("/api/global/config/custom")).json()
    positional["config"]["positional_credentials"].reverse()
    rejected = await env.client.put(
        "/api/global/config/custom",
        json=positional["config"],
        headers=headers(csrf, positional["revision"]),
    )
    assert rejected.status_code == 422
    assert code(rejected) == "unsafe_secret_reassignment"
    assert [item["username"] for item in env.store.global_value["positional_credentials"]] == [
        "position-a", "position-b",
    ]


@pytest.mark.asyncio
async def test_startup_patch_redacts_and_preserves_untouched_secret(environment: Environment):
    env = environment
    csrf = await login(env)
    response = await env.client.get("/api/startup/config/custom")
    resource = response.json()
    assert "startup-secret" not in response.text
    assert resource["meta"]["secret_fields"]["startup_token"] is True

    saved = await env.client.put(
        "/api/startup/config/custom",
        json={"set": {"listen_port": 9000}, "unset": []},
        headers=headers(csrf, resource["revision"]),
    )
    assert saved.status_code == 200
    assert env.startup.values == {"listen_port": 9000, "startup_token": "startup-secret"}
    assert saved.json()["meta"]["restart_required"] is True
    assert "startup-secret" not in saved.text


@pytest.mark.asyncio
async def test_total_pause_preserves_independent_group_choices(environment: Environment):
    env = environment
    csrf = await login(env)
    group_path = f"/api/groups/{GROUP_B}/plugins/custom/enabled"
    initial = (await env.client.get(group_path)).json()
    assert initial["config"]["enabled"] is False
    enabled = await env.client.put(group_path, json={"enabled": True}, headers=headers(csrf, initial["revision"]))
    assert enabled.status_code == 200
    assert enabled.json()["meta"]["effective"] is True
    assert env.feature_gate.resolve("custom_feature", GROUP_B)[0] is True

    global_path = "/api/plugins/custom/enabled"
    control = (await env.client.get(global_path)).json()
    stopped = await env.client.put(global_path, json={"enabled": False}, headers=headers(csrf, control["revision"]))
    assert stopped.status_code == 200
    paused = (await env.client.get(group_path)).json()
    assert paused["config"]["enabled"] is True
    assert paused["meta"]["global_enabled"] is False
    assert paused["meta"]["effective"] is False

    group_a_path = f"/api/groups/{GROUP_A}/plugins/custom/enabled"
    stale_group_a = (await env.client.get(group_a_path)).json()
    env.feature_gate.set_enabled("custom_feature", GROUP_A, False)
    group_a = (await env.client.get(f"/api/groups/{GROUP_A}/plugins/custom/enabled")).json()
    assert group_a["config"]["enabled"] is False
    rejected = await env.client.put(group_a_path, json={"enabled": True}, headers=headers(csrf, stale_group_a["revision"]))
    assert rejected.status_code == 409
    restored = await env.client.put(global_path, json={"enabled": True}, headers=headers(csrf, stopped.json()["revision"]))
    assert restored.status_code == 200
    assert (await env.client.get(group_path)).json()["meta"]["effective"] is True
    assert (await env.client.get(f"/api/groups/{GROUP_A}/plugins/custom/enabled")).json()["config"]["enabled"] is False
    fresh = (await env.client.get("/api/groups/99999/plugins/custom/enabled")).json()
    assert fresh["config"]["enabled"] is False
    assert fresh["meta"]["effective"] is False


@pytest.mark.asyncio
async def test_primary_switch_does_not_report_success_when_domain_rejects_enable(environment: Environment):
    env = environment
    csrf = await login(env)
    env.feature_gate.register(env.feature_gate.Feature(
        "custom_feature", "资格受限功能",
        getter=lambda _gid: False,
        setter=lambda _gid, _enabled: False,
    ))
    path = f"/api/groups/{GROUP_A}/plugins/custom/enabled"
    current = (await env.client.get(path)).json()
    assert current["config"]["enabled"] is True
    assert current["meta"]["effective"] is False
    denied = await env.client.put(path, json={"enabled": True}, headers=headers(csrf, current["revision"]))
    assert denied.status_code == 500
    assert code(denied) == "storage_failed"
    assert env.feature_gate.is_enabled("custom_feature", GROUP_A) is False


@pytest.mark.asyncio
async def test_owner_runtime_eligibility_does_not_rewrite_group_preference(environment: Environment):
    env = environment
    await login(env)
    env.feature_gate.set_enabled("custom_feature", GROUP_B, True)
    env.store.blocked_groups.add(GROUP_A)
    blocked = (await env.client.get(f"/api/groups/{GROUP_A}/features/custom_feature")).json()
    unaffected = (await env.client.get(f"/api/groups/{GROUP_B}/features/custom_feature")).json()
    assert blocked["config"]["enabled"] is True
    assert blocked["meta"]["effective"] is False
    assert unaffected["meta"]["effective"] is True
    env.store.blocked_groups.remove(GROUP_A)
    recovered = (await env.client.get(f"/api/groups/{GROUP_A}/features/custom_feature")).json()
    assert recovered["config"] == blocked["config"]
    assert recovered["meta"]["effective"] is True
    assert recovered["revision"] != blocked["revision"]


@pytest.mark.asyncio
async def test_declaration_media_uses_generic_authenticated_routes(environment: Environment):
    env = environment
    csrf = await login(env)
    unauthenticated_transport = httpx.ASGITransport(app=env.app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=unauthenticated_transport, base_url=BASE_URL) as anonymous:
        assert (await anonymous.get("/api/plugins/custom/media/asset.img")).status_code == 401

    wrong = await env.client.post(
        "/api/plugins/custom/media",
        content=b"PNG data",
        headers={**headers(csrf), "Content-Type": "text/plain"},
    )
    assert wrong.status_code == 415
    uploaded = await env.client.post(
        "/api/plugins/custom/media",
        content=b"PNG data",
        headers={**headers(csrf), "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200
    assert uploaded.json() == {"name": "asset.img"}
    fetched = await env.client.get("/api/plugins/custom/media/asset.img")
    assert fetched.status_code == 200
    assert fetched.content == b"PNG data"
    assert fetched.headers["content-type"].startswith("image/png")


@pytest.mark.asyncio
async def test_native_callback_failure_and_generic_retry_recovery(tmp_path: Path, isolated_feature_gate):
    failure = {"raise": True}

    async def apply(_context, _old, _new):
        if failure["raise"]:
            raise RuntimeError("private callback detail")

    declaration = configuration.register_config(
        "api_native_recovery",
        NativeModel,
        scopes=("global",),
        on_change=apply,
        name="恢复测试",
    )
    plugin = FakePlugin("xducraft_api_native_recovery", "恢复测试", declaration)
    service = AdminService(
        lambda: discover_catalog([plugin]),
        isolated_feature_gate,
        SimpleNamespace(),
        lambda: {},
    )
    app = create_app(service, AdminAuth(PASSWORD), tmp_path / "missing-dist")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        auth = await client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
        csrf = auth.json()["csrf_token"]
        current = (await client.get("/api/global/config/api_native_recovery")).json()
        failed = await client.put(
            "/api/global/config/api_native_recovery",
            json={"set": {"value": 2}, "unset": []},
            headers=headers(csrf, current["revision"]),
        )
        assert failed.status_code == 200
        assert failed.json()["meta"]["apply_status"] == "failed"
        assert "private callback detail" not in failed.text
        assert configuration.get_config("api_native_recovery").value == 1

        failure["raise"] = False
        retried = await client.post(
            "/api/global/config/api_native_recovery/apply",
            headers=headers(csrf, failed.json()["revision"]),
        )
        assert retried.status_code == 200
        assert retried.json()["meta"]["apply_status"] == "active"
        assert configuration.get_config("api_native_recovery").value == 2

        failure["raise"] = True
        failed_again = await client.put(
            "/api/global/config/api_native_recovery",
            json={"set": {"value": 3}, "unset": []},
            headers=headers(csrf, retried.json()["revision"]),
        )
        assert failed_again.json()["meta"]["apply_status"] == "failed"
        failure["raise"] = False
        rolled_back = await client.post(
            "/api/global/config/api_native_recovery/rollback",
            headers=headers(csrf, failed_again.json()["revision"]),
        )
        assert rolled_back.status_code == 200
        assert rolled_back.json()["config"]["value"] == 2
        assert rolled_back.json()["meta"]["apply_status"] == "active"
        assert configuration.get_config("api_native_recovery").value == 2


@pytest.mark.asyncio
async def test_groups_merge_live_cache_and_declared_groups(environment: Environment):
    env = environment
    await login(env)
    configuration.set_plugin_enabled("custom", False, CONTROL_ONLY_GROUP, actor="test")
    first = (await env.client.get("/api/groups")).json()
    assert {row["group_id"] for row in first["groups"]} == {str(GROUP_A), str(CONTROL_ONLY_GROUP)}
    env.service.bots()["10"].fail = True
    second = (await env.client.get("/api/groups")).json()
    assert second["groups"][0]["stale"] is True
    assert second["warnings"]


@pytest.mark.asyncio
async def test_overview_keeps_bot_ids_and_isolates_login_info_timeout(
    tmp_path: Path,
    isolated_feature_gate,
    monkeypatch: pytest.MonkeyPatch,
):
    class HangingBot(SyntheticBot):
        async def get_login_info(self):
            await asyncio.Event().wait()

    bots = {
        "10001": SyntheticBot("甲机器人"),
        "20002": HangingBot("不应出现"),
    }
    service = AdminService(
        lambda: {},
        isolated_feature_gate,
        SimpleNamespace(),
        lambda: bots,
        startup=SimpleNamespace(),
    )
    app = create_app(service, AdminAuth(PASSWORD), tmp_path / "missing-dist")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    monkeypatch.setattr("xducraft_admin.service._BOT_INFO_TIMEOUT_SECONDS", 0.01)

    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
        first = await client.get("/api/overview")
        assert first.status_code == 200
        assert first.json()["bots"] == [
            {"bot_id": "10001", "connected": True, "nickname": "甲机器人"},
            {"bot_id": "20002", "connected": True},
        ]

        bots.clear()
        bots["20002"] = SyntheticBot("乙机器人")
        second = await client.get("/api/overview")
        assert second.status_code == 200
        assert second.json()["bots"] == [
            {"bot_id": "20002", "connected": True, "nickname": "乙机器人"},
        ]




@pytest.mark.asyncio
async def test_group_resource_never_exposes_shared_secret_in_runtime_metadata(tmp_path: Path, isolated_feature_gate):
    declaration = configuration.register_config("api_scoped_secret", ScopedNativeModel)
    plugin = FakePlugin("xducraft_api_scoped_secret", "作用域边界", declaration)
    service = AdminService(lambda: discover_catalog([plugin]), isolated_feature_gate, SimpleNamespace(), lambda: {})
    app = create_app(service, AdminAuth(PASSWORD), tmp_path / "missing-dist")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
        response = await client.get(f"/api/groups/{GROUP_A}/config/api_scoped_secret")
        assert response.status_code == 200
        assert response.json()["config"] == {"value": 1}
        assert "scope-secret-marker" not in response.text
        assert "shared_token" not in response.json()["meta"]["effective"]
    assert configuration.get_config("api_scoped_secret", "group", GROUP_A).shared_token.get_secret_value() == "scope-secret-marker"


@pytest.mark.asyncio
async def test_group_draft_can_save_after_shared_settings_update(tmp_path: Path, isolated_feature_gate):
    declaration = configuration.register_config("api_modal_isolation", ScopedNativeModel)
    plugin = FakePlugin("xducraft_api_modal_isolation", "弹窗隔离", declaration)
    service = AdminService(lambda: discover_catalog([plugin]), isolated_feature_gate, SimpleNamespace(), lambda: {})
    app = create_app(service, AdminAuth(PASSWORD), tmp_path / "missing-dist")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        auth = await client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
        csrf = auth.json()["csrf_token"]
        group_path = f"/api/groups/{GROUP_A}/config/api_modal_isolation"
        group = (await client.get(group_path)).json()
        global_path = "/api/global/config/api_modal_isolation"
        shared = (await client.get(global_path)).json()
        saved_shared = await client.put(
            global_path, json={"set": {"shared_token": "changed-scope-secret"}, "unset": []},
            headers=headers(csrf, shared["revision"]),
        )
        assert saved_shared.status_code == 200
        saved_group = await client.put(
            group_path, json={"value": 5}, headers=headers(csrf, group["revision"]),
        )
        assert saved_group.status_code == 200
        assert saved_group.json()["config"] == {"value": 5}
        assert "changed-scope-secret" not in saved_group.text
