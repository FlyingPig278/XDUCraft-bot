"""NoneBot lifecycle binding for the independent configuration core."""
from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.plugin import PluginMetadata

from xducraft_bot.shared.configuration import (
    PROTOCOL_KEY, ConfigurationError, PluginConfiguration, declare_config, get_declaration, is_plugin_enabled,
)

DECLARATION = declare_config(PluginConfiguration(
    key="config", name="配置核心", managed=False,
))

__plugin_meta__ = PluginMetadata(
    name="XDUCraft 配置核心",
    description="独立的声明式配置、SQLite 存储与插件执行门禁，不依赖 WebUI。",
    usage='在业务插件导入配置声明前调用 require("xducraft_config")。',
    type="library",
    extra={PROTOCOL_KEY: DECLARATION},
)


@run_preprocessor
async def guard_plugin_execution(matcher: Matcher, event: Event):
    plugin = matcher.plugin
    if plugin is None:
        return
    metadata = plugin.metadata
    declaration = (metadata.extra or {}).get(PROTOCOL_KEY) if metadata is not None else None
    if declaration is None:
        try:
            declaration = get_declaration(plugin.id_)
        except ConfigurationError as exc:
            if exc.code == "unknown_plugin":
                return
            raise
    if not isinstance(declaration, PluginConfiguration) or not declaration.managed:
        return
    group_id = getattr(event, "group_id", None)
    if not is_plugin_enabled(declaration.key, group_id):
        raise IgnoredException("plugin_disabled_or_configuration_not_applied")


@get_driver().on_shutdown
async def close_configuration_storage():
    from xducraft_bot.shared.config_store import close_databases
    close_databases()
