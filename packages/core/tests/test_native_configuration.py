from typing import Any, Optional

import pytest
from pydantic import Field, StrictInt, StrictStr, model_validator

from xducraft_bot.shared.config_store import database
from xducraft_bot.shared.configuration import (
    ConfigContext, ConfigModel, ConfigurationError, get_config, get_declaration,
    is_plugin_enabled, recover_config, register_config, set_plugin_enabled, update_config,
)


@pytest.mark.asyncio
async def test_group_snapshot_uses_code_default_and_never_follows_global_changes():
    class Settings(ConfigModel):
        footer: Optional[str] = "initial"

    declaration = register_config("nullable_scope_regression", Settings)
    assert declaration.resources["group"].write_mode == "replace"
    await update_config("nullable_scope_regression", {"set": {"footer": "global"}})
    assert get_config("nullable_scope_regression", "group", 10002).footer == "initial"

    await update_config("nullable_scope_regression", {"footer": None}, "group", 950582991)
    await update_config("nullable_scope_regression", {"set": {"footer": "changed"}})
    assert get_config("nullable_scope_regression", "group", 950582991).footer is None
    assert get_config("nullable_scope_regression", "group", 10002).footer == "initial"


@pytest.mark.asyncio
async def test_apply_failure_pauses_only_target_and_can_restore_last_applied():
    class Settings(ConfigModel):
        maximum: StrictInt = Field(5, ge=1, le=10)

    def fail_change(context, old, new):
        if new.maximum == 6:
            raise RuntimeError("private callback details must not reach API")

    register_config("apply_failure_regression", Settings, on_change=fail_change)
    set_plugin_enabled("apply_failure_regression", True)
    set_plugin_enabled("apply_failure_regression", True, 950582991)
    set_plugin_enabled("apply_failure_regression", True, 10002)
    result = await update_config("apply_failure_regression", {"maximum": 6}, "group", 950582991)
    assert result.meta["apply_status"] == "failed"
    assert result.values["maximum"] == 6
    assert result.meta["applied"]["maximum"] == 5
    assert result.meta["effective"]["maximum"] == 5
    assert get_config("apply_failure_regression", "group", 950582991).maximum == 5
    assert not is_plugin_enabled("apply_failure_regression", 950582991)
    assert is_plugin_enabled("apply_failure_regression", 10002)
    restored = await recover_config("apply_failure_regression", ConfigContext(950582991), rollback=True)
    assert restored.values["maximum"] == 5
    assert is_plugin_enabled("apply_failure_regression", 950582991)


@pytest.mark.asyncio
async def test_invalid_candidate_cannot_replace_committed_configuration():
    class Settings(ConfigModel):
        maximum: StrictInt = Field(5, ge=1, le=10)

    register_config("validation_regression", Settings)
    set_plugin_enabled("validation_regression", True)
    with pytest.raises(ConfigurationError) as error:
        await update_config("validation_regression", {"set": {"maximum": 11}})
    assert error.value.code == "invalid_config"
    assert get_config("validation_regression").maximum == 5
    assert is_plugin_enabled("validation_regression")


def test_mutating_nested_runtime_value_cannot_change_declared_defaults():
    class Settings(ConfigModel):
        payload: Any = Field(default_factory=lambda: {"items": ["retained"]})

    register_config("snapshot_isolation_regression", Settings)
    consumer = get_config("snapshot_isolation_regression")
    consumer.payload["items"].append("local mutation")
    assert get_config("snapshot_isolation_regression").payload == {"items": ["retained"]}


def test_new_plugin_and_group_controls_are_independently_off():
    class Settings(ConfigModel):
        value: StrictInt = 1

    register_config("safe_control_defaults", Settings)
    assert not is_plugin_enabled("safe_control_defaults")
    assert not is_plugin_enabled("safe_control_defaults", 10001)
    set_plugin_enabled("safe_control_defaults", True)
    assert is_plugin_enabled("safe_control_defaults")
    assert not is_plugin_enabled("safe_control_defaults", 10001)
    set_plugin_enabled("safe_control_defaults", True, 10001)
    assert is_plugin_enabled("safe_control_defaults", 10001)
    set_plugin_enabled("safe_control_defaults", False)
    assert not is_plugin_enabled("safe_control_defaults", 10001)
    set_plugin_enabled("safe_control_defaults", True)
    assert is_plugin_enabled("safe_control_defaults", 10001)


@pytest.mark.asyncio
async def test_legacy_group_snapshot_freezes_desired_applied_split_once():
    class Settings(ConfigModel):
        value: StrictInt = 5
        token: StrictStr = Field(
            "code-secret",
            json_schema_extra={
                "x-ui-scope": "global_only",
                "x-ui-effect-phase": "startup",
            },
        )

    db = database()
    db.write_values(
        "legacy_snapshot_regression", "global", None,
        desired={"value": 8, "token": "pending-secret"},
        applied={"value": 7, "token": "active-secret"},
        status="active",
    )
    db.write_values(
        "legacy_snapshot_regression", "group", 10001,
        desired={"token": "must-not-be-local"},
        applied={"token": "must-not-be-local"},
        status="active",
    )
    register_config("legacy_snapshot_regression", Settings)
    snapshot = get_declaration("legacy_snapshot_regression").resources["group"].read(
        ConfigContext(10001)
    )
    assert snapshot.values == {"value": 8}
    assert snapshot.meta["applied"]["value"] == 7
    assert snapshot.meta["apply_status"] == "active"
    row = db.read_values("legacy_snapshot_regression", "group", 10001)
    assert row["desired"] == {"value": 8}
    assert row["applied"] == {"value": 7}
    assert get_config("legacy_snapshot_regression", "group", 10002).value == 5


@pytest.mark.asyncio
async def test_failed_global_independent_field_does_not_pause_groups_but_shared_field_does():
    class Settings(ConfigModel):
        local: StrictInt = 5
        shared: StrictInt = Field(
            1,
            json_schema_extra={"x-ui-scope": "global_only"},
        )

    def fail_change(context, old, new):
        if new.local == 6 or new.shared == 2:
            raise RuntimeError("apply failure")

    declaration = register_config("scope_failure_regression", Settings, on_change=fail_change)
    set_plugin_enabled("scope_failure_regression", True)
    set_plugin_enabled("scope_failure_regression", True, 10001)
    await update_config("scope_failure_regression", {"set": {"local": 6}})
    assert declaration.resources["global"].read(ConfigContext()).meta["apply_status"] == "failed"
    assert declaration.resources["group"].read(ConfigContext(10001)).meta["apply_status"] == "active"
    assert is_plugin_enabled("scope_failure_regression", 10001)

    await recover_config("scope_failure_regression", ConfigContext(), rollback=True)
    await update_config("scope_failure_regression", {"set": {"shared": 2}})
    assert declaration.resources["group"].read(ConfigContext(10001)).meta["apply_status"] == "failed"
    assert not is_plugin_enabled("scope_failure_regression", 10001)
    assert declaration.resources["group"].read(ConfigContext(10001)).meta["apply_scope"] == "global"
    await recover_config("scope_failure_regression", ConfigContext(), rollback=True)
    recovered = declaration.resources["group"].read(ConfigContext(10001))
    assert recovered.meta["apply_status"] == "active"
    assert recovered.meta["apply_scope"] == "group"
    assert is_plugin_enabled("scope_failure_regression", 10001)


@pytest.mark.asyncio
async def test_group_can_be_prepared_under_applied_shared_policy_while_global_update_failed():
    class Settings(ConfigModel):
        value: StrictInt = 1
        quota: StrictInt = Field(10, json_schema_extra={"x-ui-scope": "global_only"})

        @model_validator(mode="after")
        def within_quota(self):
            if self.value > self.quota:
                raise ValueError("over_quota")
            return self

    def apply(_context, _old, new):
        if new.quota == 1:
            raise RuntimeError("shared update failed")

    register_config("paused_group_preparation", Settings, on_change=apply)
    set_plugin_enabled("paused_group_preparation", True)
    set_plugin_enabled("paused_group_preparation", True, 10001)
    await update_config("paused_group_preparation", {"set": {"quota": 1}})
    await update_config("paused_group_preparation", {"value": 5}, "group", 10001)
    current = get_config("paused_group_preparation", "group", 10001)
    assert (current.value, current.quota) == (5, 10)
    assert not is_plugin_enabled("paused_group_preparation", 10001)
    await recover_config("paused_group_preparation", ConfigContext(), rollback=True)
    assert get_config("paused_group_preparation", "group", 10001).value == 5
    assert is_plugin_enabled("paused_group_preparation", 10001)


@pytest.mark.asyncio
async def test_declared_legacy_imports_are_ordered_and_fail_closed(monkeypatch):
    from xducraft_bot.shared import configuration

    completed = []

    async def import_alpha():
        completed.append("alpha")

    def import_zeta():
        completed.append("zeta")

    monkeypatch.setattr(configuration, "_registry", {
        "zeta": configuration.PluginConfiguration("zeta", "Zeta", migrate_legacy=import_zeta),
        "alpha": configuration.PluginConfiguration("alpha", "Alpha", migrate_legacy=import_alpha),
    })
    assert await configuration.migrate_legacy_configurations() == ("alpha", "zeta")
    assert completed == ["alpha", "zeta"]

    def fail_import():
        raise RuntimeError("invalid historic content")

    monkeypatch.setattr(configuration, "_registry", {
        "broken": configuration.PluginConfiguration("broken", "Broken", migrate_legacy=fail_import),
    })
    with pytest.raises(ConfigurationError) as error:
        await configuration.migrate_legacy_configurations()
    assert error.value.code == "legacy_migration_failed"
