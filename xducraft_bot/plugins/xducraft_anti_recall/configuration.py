"""反撤回配置协议；隐私、媒体和保留政策只允许全局设置。"""
from typing import List, Optional
from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator
from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, PluginConfiguration,
    declare_config, validate_values,
)
from .data_manager import store


def _field(default, title, description, order, *, phase="runtime", **bounds):
    return Field(default=default, title=title, description=description, json_schema_extra={
        "x-ui-group": "记录策略", "x-ui-order": order, "x-ui-scope": "global_only", "x-ui-effect-phase": phase,
    }, **bounds)


class AntiRecall(ConfigModel):
    cache_retention_hours: StrictInt = _field(48, "缓存保留小时", "未撤回消息的缓存保留期，下一次 04:17 清理生效。", 1, phase="next_cleanup", ge=1, le=720)
    recall_retention_days: StrictInt = _field(7, "撤回记录保留天数", "撤回记录保留期，下一次 04:17 清理生效。", 2, phase="next_cleanup", ge=1, le=365)
    max_query_results: StrictInt = _field(30, "查询条数上限", "每群一次私聊查询最多返回的记录数。", 3, ge=1, le=100)
    save_media: StrictBool = _field(True, "保存撤回媒体", "撤回发生后下载媒体，不改变既有记录。", 4)
    max_media_mb: StrictInt = _field(20, "单文件上限 MB", "后续媒体下载的单文件大小上限。", 5, ge=1, le=200)
    include_self: StrictBool = _field(False, "记录机器人自身消息", "是否缓存机器人自己发送的消息。", 6)
    exempt_user_ids: List[StrictStr] = Field(default=[], title="全局豁免 QQ", description="这些用户的消息不记录；群不能覆盖此隐私政策。", json_schema_extra={
        "x-ui-group": "记录策略", "x-ui-order": 7, "x-ui-widget": "id-list", "x-ui-scope": "global_only", "x-ui-effect-phase": "runtime",
    })

    @field_validator("exempt_user_ids")
    @classmethod
    def validate_ids(cls, values):
        if any(not value or any(c not in "0123456789" for c in value) or int(value) <= 0 for value in values):
            raise ValueError("user_ids_must_be_positive_decimal")
        return list(dict.fromkeys(str(int(value)) for value in values))


class AntiRecallGroup(ConfigModel):
    max_query_results: Optional[StrictInt] = Field(default=None, ge=1, le=100, title="本群查询条数上限", description="恢复继承使用全局值；不改变保留期、媒体或豁免策略。", json_schema_extra={
        "x-ui-group": "查询", "x-ui-order": 1, "x-ui-scope": "group_only", "x-ui-effect-phase": "runtime", "x-ui-inherit-value": None,
    })


def bind_configuration(manager):
    def read_global(ctx):
        raw = {key: value for key, value in manager.get_config().items() if key in AntiRecall.model_fields}
        values = dict(raw)
        values["exempt_user_ids"] = [str(value) for value in raw["exempt_user_ids"]]
        return ConfigSnapshot(values, revision_data=raw)

    def write_global(ctx, values):
        read_global(ctx)
        clean = validate_values(AntiRecall, values)
        clean["exempt_user_ids"] = [int(value) for value in clean["exempt_user_ids"]]
        manager.update_config(clean)

    def read_group(ctx):
        data = manager.get_config()
        raw = {"max_query_results": data["group_overrides"].get(str(ctx.group_id), {}).get("max_query_results")}
        defaults = {"max_query_results": data["max_query_results"]}
        effective = {"max_query_results": defaults["max_query_results"] if raw["max_query_results"] is None else raw["max_query_results"]}
        return ConfigSnapshot(raw, {"defaults": defaults, "effective": effective,
                                   "overridden": [key for key, value in raw.items() if value is not None]},
                              {"overrides": raw, "defaults": defaults})

    def write_group(ctx, values):
        read_group(ctx)
        manager.update_group_config(ctx.group_id, validate_values(AntiRecallGroup, values))

    return PluginConfiguration(
        key="anti_recall", name="反撤回", resources={
            "global": ConfigResource(AntiRecall, read_global, write_global),
            "group": ConfigResource(AntiRecallGroup, read_group, write_group),
        }, feature_keys=("anti_recall",), list_groups=manager.list_configured_groups,
    )


DECLARATION = declare_config(bind_configuration(store))
