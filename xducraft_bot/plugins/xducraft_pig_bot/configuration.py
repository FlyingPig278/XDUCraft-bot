"""猪猪图转发数量配置；业务开关仍由原管理器消费。"""
from typing import Optional
from pydantic import Field, StrictInt
from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, PluginConfiguration,
    declare_config, validate_values,
)
from .data_manager import pig_data_manager


class Pig(ConfigModel):
    max_forward_results: StrictInt = Field(
        default=5, ge=1, title="合并转发上限", description="查询匹配多张图片时最多随机发送的数量。",
        json_schema_extra={"x-ui-group": "查询", "x-ui-order": 1, "x-ui-scope": "global_only", "x-ui-effect-phase": "runtime"},
    )


class PigGroup(ConfigModel):
    max_forward_results: Optional[StrictInt] = Field(
        default=None, ge=1, title="本群合并转发上限", description="恢复继承后使用全局上限，不影响查询和推送开关。",
        json_schema_extra={"x-ui-group": "查询", "x-ui-order": 1, "x-ui-scope": "group_only", "x-ui-effect-phase": "runtime", "x-ui-inherit-value": None},
    )


def bind_configuration(manager):
    def read_global(ctx):
        return ConfigSnapshot({"max_forward_results": manager.get_max_forward_results()})

    def write_global(ctx, values):
        read_global(ctx)
        manager.set_max_forward_results(validate_values(Pig, values)["max_forward_results"])

    def read_group(ctx):
        data = manager._store.load()
        raw = {"max_forward_results": data["groups"].get(str(ctx.group_id), {}).get("max_forward_results")}
        defaults = {"max_forward_results": data["max_forward_results"]}
        effective = {"max_forward_results": raw["max_forward_results"] if raw["max_forward_results"] is not None else defaults["max_forward_results"]}
        return ConfigSnapshot(raw, {"defaults": defaults, "effective": effective,
                                   "overridden": [key for key, value in raw.items() if value is not None]},
                              {"overrides": raw, "defaults": defaults})

    def write_group(ctx, values):
        read_group(ctx)
        manager.update_group_config(ctx.group_id, validate_values(PigGroup, values))

    return PluginConfiguration(
        key="pig_bot", name="猪猪图", resources={
            "global": ConfigResource(Pig, read_global, write_global),
            "group": ConfigResource(PigGroup, read_group, write_group),
        }, feature_keys=("pig_query", "pig_auto_push"), list_groups=manager.list_configured_groups,
    )


DECLARATION = declare_config(bind_configuration(pig_data_manager))
