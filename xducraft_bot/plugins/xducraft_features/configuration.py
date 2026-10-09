"""QQ 功能管理是常驻系统入口，不伪造可编辑业务资源。"""
from xducraft_bot.shared.configuration import PluginConfiguration, declare_config

DECLARATION = declare_config(PluginConfiguration(
    key="features", name="QQ 功能管理", managed=False,
))
