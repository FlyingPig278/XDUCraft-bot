"""MC 更新订阅属于功能开关；版本游标仍是领域状态，不作为配置编辑。"""
from xducraft_bot.shared.configuration import PluginConfiguration, declare_config
from .data_manager import data_manager

DECLARATION = declare_config(PluginConfiguration(
    key="mc_update", name="MC 版本订阅", feature_keys=("mc_update",),
    list_groups=data_manager.get_subscribed_groups,
))
