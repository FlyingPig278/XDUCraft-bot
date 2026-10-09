"""绑定群的自助开关与部署声明；资格、领取、审计和租约仍归业务数据库。"""
from __future__ import annotations

from urllib.parse import urlparse
from pydantic import Field, SecretStr, StrictBool, StrictStr, field_validator

from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, ConfigurationError,
    PluginConfiguration, StartupConfig, declare_config,
)
from xducraft_bot.shared.deployment_config import get_startup_base, read_overrides
from . import data_manager as dm, settings


def startup_ui(order, **extra):
    return {"x-ui-group": "邀请码服务", "x-ui-order": order, "x-ui-scope": "global_only",
            "x-ui-effect-phase": "startup", **extra}


class InviteStartup(ConfigModel):
    invite_group_id: StrictStr = Field("0", pattern=r"^[0-9]+$", title="绑定群号", description="0 表示未配置；初始化后不能迁移资格到其它群", json_schema_extra=startup_ui(0, **{"x-ui-widget": "id", "x-ui-lock-source": "invite_group_locked"}))
    invite_api_url: StrictStr = Field(settings.DEFAULT_API_URL, title="邀请码 API", description="必须是包含主机名的 HTTPS 地址；重启后替换客户端", json_schema_extra=startup_ui(1))
    invite_api_secret: SecretStr = Field(SecretStr(""), title="API 密钥", description="仅写入，重启后生效；空字符串明确清空", json_schema_extra=startup_ui(2, **{"writeOnly": True, "x-ui-secret": True}))

    @field_validator("invite_group_id")
    @classmethod
    def group_id(cls, value):
        return str(int(value))

    @field_validator("invite_api_url")
    @classmethod
    def https_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError("https_url_required")
        return value


class InviteGroup(ConfigModel):
    enabled: StrictBool = Field(title="邀请码自助领取", description="仅当前绑定群，须先通过 QQ /invite init 初始化资格", json_schema_extra={"default": False, "x-ui-group": "自助领取", "x-ui-order": 0, "x-ui-scope": "group_only", "x-ui-effect-phase": "runtime"})


def status(ctx):
    current = settings.current()
    state = dm.store.get_state()
    applicable = ctx.group_id is not None and ctx.group_id == current.group_id
    available = ctx.group_id is None or applicable
    initialized = state.initialized_at is not None
    complete = not bool(current.configuration_error())
    notices = []
    if not initialized:
        notices.append({"type": "warning", "message": "请先在 QQ 使用 /invite init 初始化资格"})
    if not complete:
        notices.append({"type": "warning", "message": "邀请码部署配置不完整，保存并重启后才可开启自助领取"})
    return {"available": available, "applicable": applicable, "bound_group_id": str(current.group_id),
            "initialized": initialized, "initialized_at": state.initialized_at,
            "configuration_complete": complete, "group_config_available": applicable,
            "reason": None if available else "邀请码仅适用于当前绑定群", "notices": notices,
            "details": [{"label": "当前绑定群", "value": str(current.group_id)},
                        {"label": "资格初始化", "value": "已初始化" if initialized else "尚未初始化"},
                        {"label": "运行配置", "value": "完整" if complete else "需配置并重启"}]}


def read_group(ctx):
    meta = status(ctx)
    if not meta["applicable"]:
        raise ConfigurationError("invite_group_not_bound", "邀请码仅适用于当前绑定群")
    values = {"enabled": dm.store.get_state().self_service_enabled}
    return ConfigSnapshot(values, meta, {"values": values, **meta})


def write_group(ctx, values):
    current = read_group(ctx)
    if not current.meta["initialized"]:
        raise ConfigurationError("invite_not_initialized", "请先在 QQ 使用 /invite init 初始化")
    if values["enabled"] and not current.meta["configuration_complete"]:
        raise ConfigurationError("invite_configuration_missing", "请先配置邀请码部署参数并重启")
    dm.store.set_self_service_enabled(values["enabled"])
    if dm.store.get_state().self_service_enabled != values["enabled"]:
        raise ConfigurationError("storage_failed", "配置未能保存")


def active_startup():
    current = settings.current()
    return {"invite_group_id": str(current.group_id), "invite_api_url": current.api_url,
            "invite_api_secret": current.api_secret}


def normalize_startup(values):
    values = dict(values)
    values["invite_group_id"] = str(int(values["invite_group_id"] or 0))
    values["invite_api_url"] = str(values["invite_api_url"] or settings.DEFAULT_API_URL).strip()
    secret = values["invite_api_secret"]
    values["invite_api_secret"] = secret.get_secret_value() if isinstance(secret, SecretStr) else str(secret or "")
    return values


def base_startup():
    base = get_startup_base(settings.Config)
    if base is None:
        raise ConfigurationError("startup_base_unavailable", "启动环境配置尚未捕获")
    return normalize_startup(base.model_dump())


def validate_startup(values):
    """完整候选中仅迁移绑定群时检查锁；密钥和 URL 可独立修复。"""
    target = int(values["invite_group_id"])
    previous = int(read_overrides().get("invite_group_id", base_startup()["invite_group_id"]))
    if target == previous:
        return
    if dm.store.get_state().initialized_at is not None and target != settings.current().group_id:
        raise ConfigurationError("invite_group_locked", "初始化后的邀请码资格不能迁移到其它群", {"invite_group_id": "资格已绑定当前群"})


def startup_metadata():
    locked = dm.store.get_state().initialized_at is not None
    return {"invite_group_locked": locked, "readonly_fields": ["invite_group_id"] if locked else [],
            "notices": [{"type": "info", "message": "初始化后的邀请码资格固定绑定当前运行群，不可迁移"}] if locked else []}


def list_groups():
    active = settings.current().group_id
    pending = int(read_overrides().get("invite_group_id", base_startup()["invite_group_id"]))
    return sorted({gid for gid in (active, pending) if gid > 0})


DECLARATION = declare_config(PluginConfiguration(
    key="invite", name="邀请码", resources={"group": ConfigResource(InviteGroup, read_group, write_group)},
    list_groups=list_groups, status=status,
    startup=StartupConfig(InviteStartup, active_startup, base_startup, normalize_startup,
                          validate_startup, startup_metadata),
))
