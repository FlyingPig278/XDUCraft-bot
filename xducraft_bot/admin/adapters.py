"""Explicit bridges to already-loaded plugin-owned stores."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class PluginAdapter:
    id: str
    name: str
    loaded: bool
    feature_keys: Tuple[str, ...]
    get_group: Optional[Callable[[int], Dict[str, Any]]] = None
    put_group: Optional[Callable[[int, Dict[str, Any]], Dict[str, Any]]] = None
    get_global: Optional[Callable[[], Dict[str, Any]]] = None
    put_global: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    list_groups: Optional[Callable[[], List[int]]] = None


PLUGIN_INFO = {
    "mc_status": ("MC 服务器状态", ("mc_status",)),
    "mc_update": ("MC 版本订阅", ("mc_update",)),
    "invite": ("邀请码", ()),
    "features": ("QQ 功能管理", ()),
    "keyword": ("关键词与入群欢迎", ("keyword_reply",)),
    "anti_recall": ("反撤回", ("anti_recall",)),
    "auto_friend": ("自动好友申请", ("auto_accept_friend",)),
    "happy_bot": ("表情回应", ("emoji_reaction",)),
    "pig_bot": ("猪猪图", ("pig_query", "pig_auto_push")),
    "wordcloud": ("词云", ("wordcloud",)),
}


class DeploymentContext:
    """Loaded settings only. Never imports an unavailable plugin."""
    def __init__(self, modules: Dict[str, Any], deployment: Any):
        self.modules = modules
        self.deployment = deployment

    def values(self, *, pending: bool) -> Dict[str, Any]:
        result = {key: None for key in self.deployment.ALLOWED_KEYS}
        overrides = self.deployment.read_overrides() if pending else {}
        for name, module in self.modules.items():
            if pending:
                base = self.deployment.get_startup_base(module.Config)
                if base is None:
                    continue
                data = base.model_dump()
                data.update({key: value for key, value in overrides.items() if key in data})
            else:
                settings = module.SETTINGS
                if name == "mc_status":
                    data = {"mcs_brand": settings.brand, "mcs_title": settings.title,
                            "mcs_credit": settings.credit, "mcs_show_generated_at": settings.show_generated_at,
                            "mcs_texture": settings.texture, "mcs_width": settings.width,
                            "mcs_scale": settings.scale, "mcs_min_height": settings.min_height}
                elif name == "invite":
                    data = {"invite_group_id": settings.group_id, "invite_api_url": settings.api_url,
                            "invite_api_secret": settings.api_secret}
                else:
                    data = {"auto_accept_friend_group_ids": list(settings.group_ids)}
            if name == "mc_status":
                data["mcs_width"] = module.normalize_width(data["mcs_width"])
                data["mcs_scale"] = module.normalize_scale(data["mcs_scale"])
                data["mcs_min_height"] = module.normalize_min_height(data["mcs_min_height"])
                data["mcs_texture"] = str(data["mcs_texture"] or "").strip()
            elif name == "invite":
                data["invite_group_id"] = int(data["invite_group_id"] or 0)
                data["invite_api_url"] = str(data["invite_api_url"] or module.DEFAULT_API_URL).strip()
            else:
                data["auto_accept_friend_group_ids"] = list(dict.fromkeys(int(x) for x in data["auto_accept_friend_group_ids"] if int(x) > 0))
            result.update(data)
        if pending:
            result.update({key: value for key, value in overrides.items() if result[key] is None})
        return result

    def textures(self) -> List[str]:
        if "mc_status" not in self.modules:
            return []
        return import_module("xducraft_bot.plugins.xducraft_mc_status.raster").list_textures()

    @property
    def unavailable(self) -> List[str]:
        return [name for name in ("mc_status", "invite", "auto_friend") if name not in self.modules]


def build_service():
    import nonebot
    from xducraft_bot.shared import deployment_config, feature_gate
    from .service import AdminService

    adapters = {}
    settings_modules = {}
    invite_store = invite_settings = None
    for name, (label, keys) in PLUGIN_INFO.items():
        plugin_id = "xducraft_" + name
        plugin = nonebot.get_plugin(plugin_id)
        adapter = PluginAdapter(plugin_id, label, plugin is not None, keys)
        adapters[name] = adapter
        if plugin is None:
            continue
        root = "xducraft_bot.plugins." + plugin_id
        if name in ("features", "auto_friend"):
            if name == "auto_friend":
                settings_modules[name] = import_module(root + ".settings")
            continue
        manager = import_module(root + ".data_manager")
        if name == "mc_status":
            adapter.get_group = manager.export_group_data
            def put_mc(gid, data, manager=manager):
                manager.import_group_data(gid, data)
                return manager.export_group_data(gid)
            adapter.put_group = put_mc
            adapter.get_global = manager.export_global_data
            adapter.put_global = manager.import_global_data
            adapter.list_groups = manager.list_configured_groups
            settings_modules[name] = import_module(root + ".settings")
        elif name == "keyword":
            adapter.get_group = manager.export_scope_config
            adapter.put_group = manager.replace_scope_config
            adapter.get_global = lambda manager=manager: manager.export_scope_config(None)
            adapter.put_global = lambda data, manager=manager: manager.replace_scope_config(None, data)
            adapter.list_groups = lambda manager=manager: sorted(int(gid) for gid in manager.get_config()["groups"] if str(gid).isdigit() and int(gid) > 0)
        elif name == "happy_bot":
            adapter.get_group = lambda gid, manager=manager: {"emoji_id": manager.get_group_emoji_id(gid), "effective_emoji_id": manager.get_emoji_id(gid)}
            def put_happy(gid, data, manager=manager):
                if data["emoji_id"] is None:
                    manager.clear_group_emoji_id(gid)
                else:
                    manager.set_emoji_id(data["emoji_id"], group_id=gid)
                return {"emoji_id": manager.get_group_emoji_id(gid), "effective_emoji_id": manager.get_emoji_id(gid)}
            adapter.put_group = put_happy
            adapter.list_groups = manager.list_configured_groups
        elif name == "pig_bot":
            owned = manager.pig_data_manager
            adapter.get_global = lambda owned=owned: {"max_forward_results": owned.get_max_forward_results()}
            def put_pig(data, owned=owned):
                owned.set_max_forward_results(data["max_forward_results"])
                return {"max_forward_results": owned.get_max_forward_results()}
            adapter.put_global = put_pig
            adapter.list_groups = owned.list_configured_groups
        elif name == "wordcloud":
            owned = manager.chat_log_data_manager
            adapter.get_global = owned.load_config
            adapter.put_global = owned.update_global_config
            adapter.list_groups = owned.get_enabled_groups
        elif name == "anti_recall":
            owned = manager.store
            adapter.get_global = owned.get_config
            adapter.put_global = owned.update_config
        elif name == "mc_update":
            adapter.list_groups = manager.data_manager.get_subscribed_groups
        elif name == "invite":
            invite_store = manager.store
            module = import_module(root + ".settings")
            settings_modules[name] = module
            invite_settings = module.SETTINGS
    service = AdminService(adapters, feature_gate, deployment_config, nonebot.get_bots,
                           invite_store=invite_store, invite_settings=invite_settings)
    service.deployment_context = DeploymentContext(settings_modules, deployment_config)
    return service
