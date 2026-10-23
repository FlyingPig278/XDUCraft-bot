"""词云配置协议；保留期仅全局，群封禁始终叠加根封禁。"""
from typing import List
from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator
from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, PluginConfiguration,
    declare_config, validate_values,
)
from .data_manager import GROUP_CONFIG_KEYS, chat_log_data_manager


def _field(default, title, description, order, *, scope="global", widget=None, phase="runtime", **bounds):
    extra = {"x-ui-group": "词云", "x-ui-order": order, "x-ui-scope": {"global": "global_only", "group": "group_only"}[scope], "x-ui-effect-phase": phase}
    if widget:
        extra["x-ui-widget"] = widget
    return Field(default=default, title=title, description=description, json_schema_extra=extra, **bounds)


class _Lists(ConfigModel):
    @field_validator("ban_user_ids", check_fields=False)
    @classmethod
    def validate_ids(cls, values):
        if values is None:
            return None
        if any(not value or any(c not in "0123456789" for c in value) or int(value) <= 0 for value in values):
            raise ValueError("user_ids_must_be_positive_decimal")
        return list(dict.fromkeys(str(int(value)) for value in values))

    @field_validator("additional_stopwords", check_fields=False)
    @classmethod
    def normalize_stopwords(cls, values):
        return None if values is None else list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))


class Wordcloud(_Lists):
    ban_user_ids: List[StrictStr] = _field([], "全局封禁 QQ", "所有群都排除这些用户；群设置不能解除全局封禁。", 1, widget="id-list")
    retention_days: StrictInt = _field(1095, "日志保留天数", "只影响下一次每日 00:00 清理，不立即删除日志。", 2, phase="next_cleanup", ge=30)


class WordcloudGroup(_Lists):
    ban_user_ids: List[StrictStr] = _field([], "本群额外封禁 QQ", "与全局封禁取并集；空列表不解除全局封禁。", 1, scope="group", widget="id-list")
    min_word_length: StrictInt = _field(2, "本群最短词长", "分词后保留的最短字符数。", 2, scope="group", ge=1)
    max_words: StrictInt = _field(200, "本群最多词数", "图中最多展示的词数。", 3, scope="group", ge=20)
    additional_stopwords: List[StrictStr] = _field([], "本群额外停用词", "空列表表示不添加额外停用词。", 4, scope="group", widget="tags")
    footer_subtitle: StrictStr = _field("", "本群页脚副标题", "允许空文本。", 5, scope="group")
    footer_branding_enabled: StrictBool = _field(True, "本群显示品牌署名", "控制词云页脚品牌显示。", 6, scope="group")
    footer_branding_text: StrictStr = _field("Powered by FlyingPig278", "本群品牌署名", "允许空文本。", 7, scope="group")


def _public(values):
    result = dict(values)
    if result.get("ban_user_ids") is not None:
        result["ban_user_ids"] = [str(value) for value in result["ban_user_ids"]]
    return result


def _business(model, values):
    clean = validate_values(model, values)
    if clean["ban_user_ids"] is not None:
        clean["ban_user_ids"] = [int(value) for value in clean["ban_user_ids"]]
    return clean


def bind_configuration(manager):
    def read_global(ctx):
        raw = {key: value for key, value in manager.load_config().items() if key in Wordcloud.model_fields}
        return ConfigSnapshot(_public(raw), revision_data=raw)

    def write_global(ctx, values):
        read_global(ctx)
        manager.update_global_config(_business(Wordcloud, values))

    def read_group(ctx):
        raw = manager.export_group_config(ctx.group_id)
        effective = manager.get_effective_group_config(ctx.group_id)
        return ConfigSnapshot(_public(raw), {"effective_ban_user_ids": _public(effective)["ban_user_ids"]},
                              revision_data=raw)

    def write_group(ctx, values):
        read_group(ctx)
        manager.update_group_config(ctx.group_id, _business(WordcloudGroup, values))

    return PluginConfiguration(
        key="wordcloud", name="词云", resources={
            "global": ConfigResource(Wordcloud, read_global, write_global),
            "group": ConfigResource(WordcloudGroup, read_group, write_group),
        }, feature_keys=("wordcloud",), list_groups=manager.list_configured_groups,
        migrate_legacy=manager.load_config,
    )


DECLARATION = declare_config(bind_configuration(chat_log_data_manager))
