"""The owner panel is infrastructure, not a group-switchable business plugin."""
from xducraft_bot.shared.configuration import PluginConfiguration, declare_config

DECLARATION = declare_config(PluginConfiguration(
    key="admin", name="网页管理面板", managed=False,
))
