"""Independent per-group pig-query limits."""
from pydantic import Field, StrictInt
from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, PluginConfiguration,
    declare_config, validate_values,
)
from .data_manager import pig_data_manager


class PigGroup(ConfigModel):
    max_forward_results: StrictInt = Field(
        default=5, ge=1, title="本群合并转发上限", description="查询匹配多张图片时最多随机发送的数量。",
        json_schema_extra={"x-ui-group": "查询", "x-ui-order": 1, "x-ui-scope": "group_only",
                           "x-ui-effect-phase": "runtime"},
    )

def bind_configuration(manager):
    def read_group(ctx):
        values = manager.export_group_config(ctx.group_id)
        return ConfigSnapshot(values, revision_data=values)

    def write_group(ctx, values):
        manager.update_group_config(ctx.group_id, validate_values(PigGroup, values))

    return PluginConfiguration(
        key="pig_bot", name="猪猪图", resources={
            "group": ConfigResource(PigGroup, read_group, write_group),
        }, feature_keys=("pig_query", "pig_auto_push"),
        list_groups=manager.list_configured_groups,
        migrate_legacy=manager.migrate_legacy_config,
    )


DECLARATION = declare_config(bind_configuration(pig_data_manager))
