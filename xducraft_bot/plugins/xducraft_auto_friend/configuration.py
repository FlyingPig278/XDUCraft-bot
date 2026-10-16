"""自动好友申请的冻结白名单和实际群适用性。"""
from __future__ import annotations

from typing import Annotated
from pydantic import Field, StrictStr, field_validator

from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigurationError, PluginConfiguration, StartupConfig, declare_config,
)
from xducraft_bot.shared.deployment_config import get_startup_base, read_overrides
from xducraft_bot.shared import feature_gate
from . import settings


class AutoFriendStartup(ConfigModel):
    auto_accept_friend_group_ids: list[Annotated[StrictStr, Field(pattern=r"^[0-9]+$")]] = Field(
        default_factory=list, title="群白名单",
        description="仅接受这些群成员的好友申请。",
        json_schema_extra={"x-ui-order": 0, "x-ui-widget": "id-list",
                           "x-ui-scope": "global_only", "x-ui-effect-phase": "startup"},
    )

    @field_validator("auto_accept_friend_group_ids")
    @classmethod
    def positive_ids(cls, values):
        if any(int(value) <= 0 for value in values):
            raise ValueError("positive_group_id_required")
        return list(dict.fromkeys(str(int(value)) for value in values))


def active_startup():
    return {"auto_accept_friend_group_ids": [str(gid) for gid in settings.current().group_ids]}


def normalize_startup(values):
    return {"auto_accept_friend_group_ids": list(dict.fromkeys(str(int(gid)) for gid in values["auto_accept_friend_group_ids"] if int(gid) > 0))}


def base_startup():
    base = get_startup_base(settings.Config)
    if base is None:
        raise ConfigurationError("startup_base_unavailable", "启动环境配置尚未捕获")
    return normalize_startup(base.model_dump())


def status(ctx):
    match = ctx.group_id in settings.current().group_ids
    effective = match and feature_gate.is_enabled("auto_accept_friend", ctx.group_id)
    return {"available": True, "applicable": match, "active_whitelist_match": match,
            "feature_effective": {"auto_accept_friend": effective}, "reason": None,
            "details": [],
            "notices": [] if match else [{"type": "warning", "message": "本群不在当前运行白名单中；在全局设置添加后，需重启生效。"}]}

def list_groups():
    pending = read_overrides().get("auto_accept_friend_group_ids", base_startup()["auto_accept_friend_group_ids"])
    return sorted(set(settings.current().group_ids) | {int(gid) for gid in pending if int(gid) > 0})



DECLARATION = declare_config(PluginConfiguration(
    key="auto_friend", name="自动好友申请", feature_keys=("auto_accept_friend",),
    list_groups=list_groups, status=status,
    startup=StartupConfig(AutoFriendStartup, active_startup, base_startup, normalize_startup),
))
