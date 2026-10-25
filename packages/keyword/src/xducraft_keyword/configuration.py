"""关键词配置的安全消息段模型；CQ 与时间戳只用于领域存储和版本计算。"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union
from pydantic import ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, ConfigurationError,
    PluginConfiguration, declare_config,
)
from . import data_manager as dm
from .reply_codec import MediaProvider, replies_to_segments, segments_to_replies


def ui(group, order, *, scope="group", **extra):
    return {"x-ui-group": group, "x-ui-order": order, "x-ui-scope": {"group": "group_only"}[scope],
            "x-ui-effect-phase": "runtime", **extra}


class TextSegment(ConfigModel):
    model_config = ConfigDict(title="文字")
    type: Literal["text"] = "text"
    text: StrictStr = Field(min_length=1, title="文字", description="CQ 形式的文字也只作为纯文字发送")


class ImageSegment(ConfigModel):
    model_config = ConfigDict(title="本地图片")
    type: Literal["image"] = "image"
    name: StrictStr = Field(pattern=r"^[a-f0-9]{32}\.img$", title="本地图片", description="仅已上传且有效的本地图片名", json_schema_extra={"x-ui-widget": "image"})


class FaceSegment(ConfigModel):
    model_config = ConfigDict(title="QQ 表情")
    type: Literal["face"] = "face"
    id: StrictStr = Field(pattern=r"^[0-9]+$", title="QQ 表情 ID", description="十进制数字字符串")


class AtSegment(ConfigModel):
    model_config = ConfigDict(title="@ 成员")
    type: Literal["at"] = "at"
    qq: StrictStr = Field(pattern=r"^(?:all|[1-9][0-9]*)$", title="提及对象", description="正整数 QQ 号或 all（全体成员）")


class OpaqueReference(ConfigModel):
    reply_index: StrictInt = Field(ge=0, title="原回复位置")
    segment_index: StrictInt = Field(ge=0, title="原消息段位置")


class OpaqueSegment(ConfigModel):
    model_config = ConfigDict(title="不可编辑消息", extra="forbid", json_schema_extra={"readOnly": True})
    type: Literal["opaque"] = "opaque"
    ref: OpaqueReference = Field(title="原消息段引用", description="仅同一规则或本群欢迎的旧消息段可保留")
    label: StrictStr = Field(title="不可编辑消息", description="可移动、删除，不能创建或跨规则复制")


Segment = Annotated[Union[TextSegment, ImageSegment, FaceSegment, AtSegment, OpaqueSegment], Field(discriminator="type")]
MessageSegments = Annotated[list[Segment], Field(min_length=1, json_schema_extra={"x-ui-widget": "message_segments"})]
Replies = list[MessageSegments]


class Rule(ConfigModel):
    id: Optional[StrictStr] = Field(default=None, title="规则标识", description="新规则为 null；旧规则必须保留原标识", json_schema_extra={"readOnly": True})
    keywords: list[Annotated[StrictStr, Field(min_length=1, max_length=64)]] = Field(min_length=1, title="关键词", description="去空白后每词最多 64 字；同一规则内不重复", json_schema_extra=ui("触发条件", 0, **{"x-ui-widget": "tags"}))
    match: Literal["contains", "exact", "prefix", "regex"] = Field("contains", title="匹配方式", description="包含、完全匹配、开头匹配或合法正则", json_schema_extra=ui("触发条件", 1))
    enabled: StrictBool = Field(True, title="启用规则", description="停用规则保留内容但不参与匹配", json_schema_extra=ui("触发条件", 2))
    cooldown: StrictInt = Field(0, ge=0, le=86400, title="冷却秒数", description="0 明确表示使用默认冷却", json_schema_extra=ui("触发条件", 3))
    replies: Replies = Field(min_length=1, max_length=8, title="回复消息", description="按顺序发送 1–8 条；每条转换 CQ 后最多 4096 字符", json_schema_extra=ui("回复", 4, **{"x-ui-widget": "reply_variants", "x-ui-item-widget": "message_segments"}))

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, values):
        result = [value.strip() for value in values]
        if any(not value for value in result):
            raise ValueError("empty_keyword")
        if len({value.casefold() for value in result}) != len(result):
            raise ValueError("duplicate_keyword")
        return result

    @field_validator("id")
    @classmethod
    def identity(cls, value):
        if value is not None and (not value or value != value.strip()):
            raise ValueError("invalid_rule_id")
        return value

    @model_validator(mode="after")
    def regex(self):
        if self.match == "regex" and any(not dm.is_valid_regex(value) for value in self.keywords):
            raise ValueError("invalid_regex")
        return self


class KeywordGroup(ConfigModel):
    rules: list[Rule] = Field(max_length=dm.MAX_RULES_PER_SCOPE, title="本群规则", description="按列表顺序首个匹配生效", json_schema_extra=ui("规则", 0, scope="group", default=[], **{"x-ui-widget": "ordered_object_list", "x-ui-label-field": "keywords"}))
    join_replies: Replies = Field(max_length=8, title="入群欢迎", description="0–8 条；发送首条时自动 @ 新成员，不在配置中插入该 @", json_schema_extra=ui("入群欢迎", 1, scope="group", default=[], **{"x-ui-widget": "reply_variants", "x-ui-item-widget": "message_segments"}))
    default_cooldown: StrictInt = Field(default=10, ge=0, le=3600, title="本群默认冷却", description="秒数；0 表示无冷却", json_schema_extra=ui("冷却", 2, scope="group", default=10))

    @model_validator(mode="after")
    def unique_rules(self):
        seen_ids = set()
        for rule in self.rules:
            if rule.id is not None:
                if rule.id in seen_ids:
                    raise ValueError("duplicate_rule_id")
                seen_ids.add(rule.id)
        return self


def read_scope(ctx):
    raw = dm.export_scope_config(ctx.group_id)
    values = dict(raw)
    values["rules"] = [{**{key: value for key, value in rule.items() if key not in ("created_at", "replies")},
                        "replies": replies_to_segments(rule["replies"])} for rule in raw["rules"]]
    values["join_replies"] = replies_to_segments(raw["join_replies"])
    meta = {"rule_created_at": {rule["id"]: rule.get("created_at") for rule in raw["rules"]}}
    return ConfigSnapshot(values, meta, {"values": raw})


def write_scope(ctx, values):
    raw = dm.export_scope_config(ctx.group_id)
    old = {rule["id"]: rule for rule in raw["rules"]}
    if len(old) != len(raw["rules"]):
        raise ConfigurationError("invalid_config", "旧规则标识重复，无法确定消息引用", {"rules": "请先修复规则标识"})
    seen = set()
    try:
        for rule in values["rules"]:
            identity = rule["id"]
            if identity is not None:
                if identity not in old or identity in seen:
                    raise ValueError("invalid_rule_id")
                seen.add(identity)
            rule["replies"] = segments_to_replies(rule["replies"], old[identity]["replies"] if identity is not None else [])
        values["join_replies"] = segments_to_replies(values["join_replies"], raw["join_replies"])
        dm.replace_scope_config(ctx.group_id, values)
    except ValueError:
        raise ConfigurationError("invalid_config", "消息段、规则引用或关键词不合法", {"rules": "请检查内容和原消息引用"}) from None


def list_groups():
    return sorted(int(gid) for gid in dm.get_config()["groups"] if str(gid).isdigit() and int(gid) > 0)


DECLARATION = declare_config(PluginConfiguration(
    key="keyword", name="关键词与入群欢迎", feature_keys=("keyword_reply",),
    resources={"group": ConfigResource(KeywordGroup, read_scope, write_scope)},
    list_groups=list_groups, media=MediaProvider, migrate_legacy=dm.migrate_legacy_config,
))
