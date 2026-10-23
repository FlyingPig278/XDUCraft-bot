"""Independent group emoji-reaction settings."""
from pydantic import Field, StrictStr, field_validator

from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, PluginConfiguration,
    declare_config, validate_values,
)
from . import data_manager


class Happy(ConfigModel):
    emoji_id: StrictStr = Field(
        default=data_manager.DEFAULT_EMOJI_ID, title="本群表情 ID", description="本群直接使用的数字表情 ID。",
        json_schema_extra={"x-ui-group": "表情回应", "x-ui-order": 1, "x-ui-scope": "group_only",
                           "x-ui-effect-phase": "runtime"},
    )

    @field_validator("emoji_id")
    @classmethod
    def validate_emoji(cls, value):
        if not value or any(c not in "0123456789" for c in value):
            raise ValueError("emoji_id_must_be_decimal")
        return value


def bind_configuration(manager=data_manager):
    def read(ctx):
        value = manager.get_emoji_id(ctx.group_id)
        return ConfigSnapshot({"emoji_id": value}, revision_data={"emoji_id": value})

    def write(ctx, values):
        clean = validate_values(Happy, values)
        manager.set_emoji_id(clean["emoji_id"], group_id=ctx.group_id)

    return PluginConfiguration(
        key="happy_bot", name="表情回应",
        resources={"group": ConfigResource(Happy, read, write)},
        feature_keys=("emoji_reaction",), list_groups=manager.list_configured_groups,
        migrate_legacy=manager.migrate_legacy_config,
    )


DECLARATION = declare_config(bind_configuration())
