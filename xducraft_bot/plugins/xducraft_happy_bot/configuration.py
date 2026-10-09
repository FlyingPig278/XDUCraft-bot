"""群表情设置协议；QQ 的根默认值仅作为只读继承来源。"""
from typing import Optional

from pydantic import Field, StrictStr, field_validator

from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, PluginConfiguration,
    declare_config, validate_values,
)
from . import data_manager


class Happy(ConfigModel):
    emoji_id: Optional[StrictStr] = Field(
        default=None, title="本群表情 ID", description="数字表情 ID；恢复继承使用已有根默认值，不修改其他群。",
        json_schema_extra={"x-ui-group": "表情回应", "x-ui-order": 1, "x-ui-scope": "group_only",
                           "x-ui-effect-phase": "runtime", "x-ui-inherit-value": None},
    )

    @field_validator("emoji_id")
    @classmethod
    def validate_emoji(cls, value):
        if value is not None and (not value or any(c not in "0123456789" for c in value)):
            raise ValueError("emoji_id_must_be_decimal")
        return value


def bind_configuration(manager=data_manager):
    def read(ctx):
        data = manager._store.load()
        raw = data["groups"].get(str(ctx.group_id))
        root = data["emoji_id"]
        return ConfigSnapshot(
            {"emoji_id": raw},
            {"defaults": {"emoji_id": root}, "effective": {"emoji_id": raw or root},
             "effective_emoji_id": raw or root, "overridden": ["emoji_id"] if raw is not None else []},
            {"override": raw, "default": root},
        )

    def write(ctx, values):
        read(ctx)
        clean = validate_values(Happy, values)
        if clean["emoji_id"] is None:
            manager.clear_group_emoji_id(ctx.group_id)
        else:
            manager.set_emoji_id(clean["emoji_id"], group_id=ctx.group_id)

    return PluginConfiguration(
        key="happy_bot", name="表情回应", resources={"group": ConfigResource(Happy, read, write)},
        feature_keys=("emoji_reaction",), list_groups=manager.list_configured_groups,
    )


DECLARATION = declare_config(bind_configuration())
