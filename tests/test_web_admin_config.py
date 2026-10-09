from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from xducraft_bot.shared import deployment_config as deployment
from xducraft_bot.shared.json_store import JsonStore


@pytest.fixture
def isolated_deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "shared" / "data" / "deployment_overrides.json"
    monkeypatch.setattr(deployment, "DEPLOYMENT_OVERRIDES_PATH", path)
    monkeypatch.setattr(deployment, "_STORE", JsonStore(str(path), dict))
    monkeypatch.setattr(deployment, "_STARTUP_READY", False)
    monkeypatch.setattr(deployment, "_STARTUP_OVERRIDES", {})
    monkeypatch.setattr(deployment, "_STARTUP_ERROR", None)
    monkeypatch.setattr(deployment, "_STARTUP_BASES", {})
    return path


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_exact_allowlist_and_sparse_atomic_update(isolated_deployment: Path) -> None:
    assert set(deployment.DEPLOYMENT_OVERRIDE_KEYS) == {
        "mcs_brand",
        "mcs_title",
        "mcs_credit",
        "mcs_show_generated_at",
        "mcs_texture",
        "mcs_width",
        "mcs_scale",
        "mcs_min_height",
        "invite_group_id",
        "invite_api_url",
        "invite_api_secret",
        "auto_accept_friend_group_ids",
    }

    saved = deployment.update_overrides(
        {
            "mcs_width": 800,
            "invite_api_secret": "do-not-disclose",
            "auto_accept_friend_group_ids": [10001, 10001, 10002],
        },
        [],
    )
    assert saved == {
        "mcs_width": 800,
        "invite_api_secret": "do-not-disclose",
        "auto_accept_friend_group_ids": [10001, 10002],
    }

    saved = deployment.update_overrides(
        {"mcs_scale": 4, "invite_api_url": "https://example.test/invite"},
        ["mcs_width"],
    )
    assert saved == {
        "invite_api_secret": "do-not-disclose",
        "auto_accept_friend_group_ids": [10001, 10002],
        "mcs_scale": 4,
        "invite_api_url": "https://example.test/invite",
    }
    assert deployment.read_overrides() == saved
    if os.name != "nt":
        assert stat.S_IMODE(isolated_deployment.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "values",
    [
        {"unknown": 1},
        {"mcs_width": 479},
        {"mcs_width": True},
        {"mcs_scale": 3},
        {"mcs_min_height": -1},
        {"mcs_texture": "../stone.png"},
        {"invite_group_id": -1},
        {"invite_api_url": "http://example.test/invite"},
        {"invite_api_url": "https:///missing-host"},
        {"auto_accept_friend_group_ids": [0]},
        {"auto_accept_friend_group_ids": ["10001"]},
    ],
)
def test_invalid_update_is_value_free_and_preserves_file(
    isolated_deployment: Path, values: dict[str, object]
) -> None:
    _write_json(isolated_deployment, {"mcs_width": 640})
    original = isolated_deployment.read_bytes()

    with pytest.raises(deployment.DeploymentConfigError) as caught:
        deployment.update_overrides(values, [])

    assert str(caught.value) == deployment.DEPLOYMENT_CONFIG_INVALID
    assert isolated_deployment.read_bytes() == original


def test_set_unset_overlap_is_rejected_without_write(isolated_deployment: Path) -> None:
    _write_json(isolated_deployment, {"mcs_width": 640})
    original = isolated_deployment.read_bytes()

    with pytest.raises(deployment.DeploymentConfigError):
        deployment.update_overrides({"mcs_width": 800}, ["mcs_width"])

    assert isolated_deployment.read_bytes() == original


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        "[]",
        '{"unknown": true}',
        '{"mcs_width": "800"}',
        "[" * 1500 + "0" + "]" * 1500,
        '{"mcs_width":' + "9" * 5000 + "}",
    ],
)
def test_corrupt_file_never_falls_back_or_rewrites(
    isolated_deployment: Path, content: str
) -> None:
    isolated_deployment.parent.mkdir(parents=True, exist_ok=True)
    isolated_deployment.write_text(content, encoding="utf-8")
    original = isolated_deployment.read_bytes()

    with pytest.raises(deployment.DeploymentConfigError) as caught:
        deployment.read_overrides()
    assert str(caught.value) == deployment.DEPLOYMENT_CONFIG_INVALID

    with pytest.raises(deployment.DeploymentConfigError):
        deployment.update_overrides({"mcs_width": 800}, [])
    assert isolated_deployment.read_bytes() == original


def test_startup_snapshot_and_base_are_immutable(isolated_deployment: Path) -> None:
    class RenderConfig(BaseModel):
        mcs_width: int = 640
        mcs_scale: int = 2
        environment_marker: str = "initial"

    class FriendConfig(BaseModel):
        auto_accept_friend_group_ids: list[int] = Field(default_factory=list)

    _write_json(
        isolated_deployment,
        {
            "mcs_width": 800,
            "auto_accept_friend_group_ids": [10001, 10002],
        },
    )

    first = deployment.apply_startup_overrides(RenderConfig())
    assert first.mcs_width == 800
    assert first.mcs_scale == 2
    assert first.environment_marker == "initial"

    deployment.update_overrides(
        {"mcs_width": 1200, "auto_accept_friend_group_ids": [20001]}, []
    )
    repeated = deployment.apply_startup_overrides(
        RenderConfig(mcs_width=700, mcs_scale=4, environment_marker="later")
    )
    friends = deployment.apply_startup_overrides(FriendConfig())

    assert repeated.model_dump() == first.model_dump()
    assert friends.auto_accept_friend_group_ids == [10001, 10002]
    base = deployment.get_startup_base(RenderConfig)
    assert base is not None
    assert base.model_dump() == {
        "mcs_width": 640,
        "mcs_scale": 2,
        "environment_marker": "initial",
    }
    base.mcs_width = 999
    assert deployment.get_startup_base(RenderConfig).mcs_width == 640  # type: ignore[union-attr]
    assert deployment.get_startup_overrides()["mcs_width"] == 800


def test_startup_failure_is_shared_and_sticky_but_live_read_recovers(
    isolated_deployment: Path,
) -> None:
    class RenderConfig(BaseModel):
        mcs_width: int = 640

    class InviteConfig(BaseModel):
        invite_group_id: int = 0

    isolated_deployment.parent.mkdir(parents=True, exist_ok=True)
    isolated_deployment.write_text("not-json", encoding="utf-8")

    with pytest.raises(deployment.DeploymentConfigError):
        deployment.apply_startup_overrides(RenderConfig())
    assert deployment.get_startup_failure() == deployment.DEPLOYMENT_CONFIG_INVALID

    _write_json(isolated_deployment, {"mcs_width": 800, "invite_group_id": 10001})
    assert deployment.read_overrides()["mcs_width"] == 800
    with pytest.raises(deployment.DeploymentConfigError):
        deployment.apply_startup_overrides(InviteConfig())

    assert deployment.get_startup_base(RenderConfig).mcs_width == 640  # type: ignore[union-attr]
    assert deployment.get_startup_base(InviteConfig).invite_group_id == 0  # type: ignore[union-attr]
