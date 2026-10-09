from typing import Any, Optional

import pytest
from pydantic import Field, StrictInt

from xducraft_bot.shared.configuration import (
    ConfigContext, ConfigModel, ConfigurationError, get_config, is_plugin_enabled,
    recover_config, register_config, update_config,
)


@pytest.mark.asyncio
async def test_explicit_null_detaches_group_from_later_global_default():
    class Settings(ConfigModel):
        footer: Optional[str] = "initial"

    register_config("nullable_scope_regression", Settings)
    await update_config("nullable_scope_regression", {"set": {"footer": None}}, "group", 950582991)
    await update_config("nullable_scope_regression", {"set": {"footer": "changed"}})
    assert get_config("nullable_scope_regression", "group", 950582991).footer is None
    assert get_config("nullable_scope_regression", "group", 10002).footer == "changed"
    await update_config("nullable_scope_regression", {"unset": ["footer"]}, "group", 950582991)
    assert get_config("nullable_scope_regression", "group", 950582991).footer == "changed"


@pytest.mark.asyncio
async def test_apply_failure_pauses_only_target_and_can_restore_last_applied():
    class Settings(ConfigModel):
        maximum: StrictInt = Field(5, ge=1, le=10)

    def fail_change(context, old, new):
        if new.maximum == 6:
            raise RuntimeError("private callback details must not reach API")

    register_config("apply_failure_regression", Settings, on_change=fail_change)
    result = await update_config("apply_failure_regression", {"set": {"maximum": 6}}, "group", 950582991)
    assert result.meta["apply_status"] == "failed"
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
