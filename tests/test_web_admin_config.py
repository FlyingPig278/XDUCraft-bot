from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from pydantic import BaseModel, Field, SecretStr, StrictInt

from xducraft_bot.admin.startup import StartupResources
from xducraft_bot.shared.configuration import ConfigModel, ConfigurationError, PluginConfiguration, StartupConfig
from xducraft_bot.shared import deployment_config as deployment
from xducraft_bot.shared.json_store import JsonStore


@pytest.fixture
def isolated_deployment(tmp_path, monkeypatch):
    path = tmp_path / "deployment_overrides.json"
    monkeypatch.setattr(deployment, "DEPLOYMENT_OVERRIDES_PATH", path)
    monkeypatch.setattr(deployment, "_STORE", JsonStore(str(path), dict))
    monkeypatch.setattr(deployment, "_STARTUP_READY", False)
    monkeypatch.setattr(deployment, "_STARTUP_OVERRIDES", {})
    monkeypatch.setattr(deployment, "_STARTUP_ERROR", None)
    monkeypatch.setattr(deployment, "_STARTUP_BASES", {})
    return path


class PublicSettings(ConfigModel):
    width: StrictInt = Field(640, ge=480, le=1600)
    api_key: SecretStr = SecretStr("environment-secret")


class BootSettings(BaseModel):
    width: int = 640
    api_key: str = "environment-secret"


@pytest.fixture
def startup_resource(isolated_deployment):
    active = deployment.apply_startup_overrides(BootSettings())
    declaration = PluginConfiguration("startup_contract_regression", "Startup", startup=StartupConfig(
        PublicSettings, lambda: active.model_dump(),
        lambda: deployment.get_startup_base(BootSettings).model_dump(), dict,
    ))
    return StartupResources(deployment), declaration


def test_declared_sparse_update_preserves_unloaded_plugin_values(startup_resource, isolated_deployment):
    isolated_deployment.write_text(json.dumps({"unloaded_plugin_option": 42}), encoding="utf-8")
    helper, declaration = startup_resource
    result = helper.write(declaration, {"set": {"width": 800, "api_key": "pending-secret"}})
    assert result.values["width"] == 800
    assert result.meta["active"]["width"] == 640
    assert result.meta["restart_required"]
    assert deployment.read_overrides() == {"width": 800, "api_key": "pending-secret", "unloaded_plugin_option": 42}
    result = helper.write(declaration, {"unset": ["width"]})
    assert result.values["width"] == 640
    assert "width" not in deployment.read_overrides()
    assert deployment.read_overrides()["unloaded_plugin_option"] == 42
    if os.name != "nt":
        assert stat.S_IMODE(isolated_deployment.stat().st_mode) == 0o600


@pytest.mark.parametrize("patch", [
    {"set": {"unknown": 1}}, {"set": {"width": 479}}, {"set": {"width": True}},
    {"set": {"width": 1601}}, {"set": {"width": "800"}},
    {"set": {"width": 800}, "unset": ["width"]}, {"unset": ["width", "width"]},
    {"unset": ["unknown"]}, {"set": []},
])
def test_invalid_candidate_never_replaces_saved_file(startup_resource, isolated_deployment, patch):
    helper, declaration = startup_resource
    helper.write(declaration, {"set": {"width": 800}})
    original = isolated_deployment.read_bytes()
    with pytest.raises(ConfigurationError):
        helper.write(declaration, patch)
    assert isolated_deployment.read_bytes() == original
    assert helper.read(declaration).values["width"] == 800


@pytest.mark.parametrize("content", ["{broken", "[]", "{\"width\":NaN}", "[" * 1500 + "0" + "]" * 1500])
def test_corrupt_document_never_falls_back_or_rewrites(isolated_deployment, content):
    isolated_deployment.write_text(content, encoding="utf-8")
    original = isolated_deployment.read_bytes()
    with pytest.raises(deployment.DeploymentConfigError):
        deployment.read_overrides()
    with pytest.raises(deployment.DeploymentConfigError):
        deployment.update_overrides({"width": 800}, [])
    assert isolated_deployment.read_bytes() == original


def test_semantically_invalid_saved_value_is_not_silently_normalized(startup_resource, isolated_deployment):
    helper, declaration = startup_resource
    isolated_deployment.write_text('{"width":"invalid"}', encoding="utf-8")
    original = isolated_deployment.read_bytes()
    with pytest.raises(ConfigurationError):
        helper.read(declaration)
    assert isolated_deployment.read_bytes() == original


def test_startup_snapshot_and_base_remain_immutable_after_save(isolated_deployment):
    class RenderConfig(BaseModel):
        width: int = 640
        environment_marker: str = "initial"

    class FriendConfig(BaseModel):
        group_ids: list[int] = Field(default_factory=list)

    deployment.update_overrides({"width": 800, "group_ids": [10001, 10002]}, [])
    first = deployment.apply_startup_overrides(RenderConfig())
    deployment.update_overrides({"width": 1200, "group_ids": [20001]}, [])
    repeated = deployment.apply_startup_overrides(RenderConfig(width=700, environment_marker="later"))
    assert repeated.model_dump() == first.model_dump()
    assert first.width == 800
    assert deployment.apply_startup_overrides(FriendConfig()).group_ids == [10001, 10002]
    base = deployment.get_startup_base(RenderConfig)
    assert base.width == 640
    base.width = 999
    assert deployment.get_startup_base(RenderConfig).width == 640


def test_startup_file_failure_is_shared_sticky_and_live_read_can_recover(isolated_deployment):
    class RenderConfig(BaseModel):
        width: int = 640

    class OtherConfig(BaseModel):
        group_id: int = 0

    isolated_deployment.write_text("not-json", encoding="utf-8")
    with pytest.raises(deployment.DeploymentConfigError):
        deployment.apply_startup_overrides(RenderConfig())
    isolated_deployment.write_text('{"width":800,"group_id":10001}', encoding="utf-8")
    assert deployment.read_overrides()["width"] == 800
    with pytest.raises(deployment.DeploymentConfigError):
        deployment.apply_startup_overrides(OtherConfig())
    assert deployment.get_startup_base(RenderConfig).width == 640
    assert deployment.get_startup_base(OtherConfig).group_id == 0
