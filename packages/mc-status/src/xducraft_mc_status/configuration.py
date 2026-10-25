"""MC 的配置、服务器树校验和冻结部署配置声明。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from xducraft_bot.shared.configuration import (
    ConfigModel, ConfigResource, ConfigSnapshot, ConfigurationError,
    PluginConfiguration, StartupConfig, declare_config,
)
from xducraft_bot.shared.deployment_config import get_startup_base, read_overrides
from . import data_manager as dm, settings
from .utils import is_valid_api_url, is_valid_server_address

AuthMode = Literal["", "official", "mua", "xdu", "yggdrasil", "offline", "mixed"]
Source = Literal["protocol", "sjtu", "jsu", "custom", "auto", "auto_api_first"]


def ui(group, order, *, scope="group", **extra):
    return {"x-ui-group": group, "x-ui-order": order, "x-ui-scope": {"global": "global_only", "group": "group_only"}[scope],
            "x-ui-effect-phase": "runtime", **extra}


class Server(ConfigModel):
    ip: StrictStr = Field(title="服务器地址", description="host[:port]，全树地址去空白后须唯一", json_schema_extra=ui("服务器", 0))
    comment: StrictStr = Field("", title="备注", description="服务器说明文字", json_schema_extra=ui("服务器", 1))
    tag: StrictStr = Field("", title="标签", description="列表中的短标签", json_schema_extra=ui("服务器", 2))
    tag_color: StrictStr = Field("", title="标签颜色", description="留空或六位十六进制颜色，不含 #", pattern=r"^(?:[A-Fa-f0-9]{6})?$", json_schema_extra=ui("服务器", 3))
    ignore_in_list: StrictBool = Field(False, title="不在总览显示", description="单独查询仍可用", json_schema_extra=ui("服务器", 4))
    hide_ip: StrictBool = Field(False, title="隐藏原地址", description="开启后显示自定义地址；自定义地址为空时不显示地址", json_schema_extra=ui("服务器", 5))
    display_name: StrictStr = Field("", title="自定义显示地址", description="保留此值直到明确修改，关闭隐藏地址不会自动清空", json_schema_extra=ui("服务器", 6))
    auth_mode: AuthMode = Field("", title="登录认证", description="空字符串表示未配置，使用群默认认证", json_schema_extra=ui("服务器", 7, **{"x-ui-inherit-value": ""}))
    priority: Optional[StrictInt] = Field(None, title="排序优先级", description="任意整数，未设置按 100 排序；普通保存不重排", json_schema_extra=ui("服务器", 8))
    children: list[Server] = Field(default_factory=list, title="子服务器", description="父节点本身也是服务器；删除父节点会删除后代", json_schema_extra=ui("服务器", 9))

    @field_validator("ip")
    @classmethod
    def address(cls, value):
        value = value.strip()
        if not is_valid_server_address(value):
            raise ValueError("server_address")
        return value





class MCGroup(ConfigModel):
    servers: list[Server] = Field(title="服务器树", description="地址全树唯一，最多十三层；同级按优先级和原顺序显示", json_schema_extra=ui("服务器列表", 0, default=[], **{"x-ui-widget": "tree", "x-ui-tree": {"children": "children", "label": "ip", "order": "priority", "default-order": 100, "max-depth": 13}}))
    footer: StrictStr = Field(title="页脚", description="状态列表底部文字", json_schema_extra=ui("显示", 1, default=""))
    show_offline_by_default: StrictBool = Field(title="默认显示离线服务器", description="总览是否包含离线节点", json_schema_extra=ui("显示", 2, default=False))
    status_api_source: Source = Field(title="本群查询源", description="本群直接使用的查询源", json_schema_extra=ui("状态查询", 3, default="auto"))
    status_api_url: StrictStr = Field(title="本群 API 地址", description="留空表示未配置自定义 API", json_schema_extra=ui("状态查询", 4, default=""))
    default_auth_mode: AuthMode = Field(title="默认登录认证", description="空字符串表示未设置默认认证", json_schema_extra=ui("状态查询", 5, default=""))
    auth_detect: StrictBool = Field(title="协议认证探测", description="协议无法可靠区分联合认证后端，建议关闭", json_schema_extra=ui("状态查询", 6, default=False))
    quiet_admin_replies: StrictBool = Field(title="管理回执私聊发送", description="减少群内管理回执", json_schema_extra=ui("显示", 7, default=True))

    @field_validator("status_api_url")
    @classmethod
    def url(cls, value):
        if value and not is_valid_api_url(value):
            raise ValueError("api_url")
        return value

    @model_validator(mode="after")
    def unique_tree(self):
        seen = set()
        def walk(nodes, depth):
            if nodes and depth > 12:
                raise ValueError("tree_depth")
            for node in nodes:
                if node.ip in seen:
                    raise ValueError("duplicate_server_address")
                seen.add(node.ip)
                walk(node.children, depth + 1)
        walk(self.servers, 0)
        return self



def read_group(ctx):
    raw = dm.export_group_data(ctx.group_id)
    return ConfigSnapshot(raw, revision_data={"configured": ctx.group_id in dm.list_configured_groups(), "values": raw})



def write_group(ctx, values):
    def omit_priority(nodes):
        for node in nodes:
            if node.get("priority") is None:
                node.pop("priority", None)
            omit_priority(node["children"])
    omit_priority(values["servers"])
    dm.import_group_data(ctx.group_id, values)


def startup_ui(order):
    return {"x-ui-group": "状态图外观", "x-ui-order": order, "x-ui-scope": "global_only", "x-ui-effect-phase": "startup"}


class MCStartup(ConfigModel):
    mcs_brand: StrictStr = Field(settings.DEFAULT_BRAND, title="品牌", description="留空不绘制，支持 § 颜色码", json_schema_extra=startup_ui(0))
    mcs_title: StrictStr = Field(settings.DEFAULT_TITLE, title="标题", description="留空不绘制，支持 § 颜色码", json_schema_extra=startup_ui(1))
    mcs_credit: StrictStr = Field(settings.DEFAULT_CREDIT, title="署名", description="留空不绘制，支持 § 颜色码", json_schema_extra=startup_ui(2))
    mcs_show_generated_at: StrictBool = Field(True, title="显示生成时间", description="在图像底栏显示生成时间", json_schema_extra=startup_ui(3))
    mcs_texture: StrictStr = Field("", title="背景材质", description="空值按群稳定选择；random 随机；none 不铺材质；或已有 PNG 文件名", json_schema_extra={**startup_ui(4), "x-ui-options-source": "mcs_texture"})
    mcs_width: StrictInt = Field(640, ge=480, le=1600, title="画布宽度", description="逻辑像素宽度", json_schema_extra=startup_ui(5))
    mcs_scale: Literal[2, 4] = Field(2, title="缩放倍率", description="仅 2 或 4，保持像素字体网格", json_schema_extra=startup_ui(6))
    mcs_min_height: StrictInt = Field(480, ge=0, title="最小高度", description="0 表示随内容收缩", json_schema_extra=startup_ui(7))

    @field_validator("mcs_scale", mode="before")
    @classmethod
    def strict_scale(cls, value):
        if type(value) is not int:
            raise ValueError("scale_type")
        return value

    @field_validator("mcs_texture")
    @classmethod
    def texture_name(cls, value):
        if value not in ("", "random", "none") and (not value.endswith(".png") or "/" in value or "\\" in value or ":" in value or value in (".", "..")):
            raise ValueError("texture_name")
        return value


def active_startup():
    current = settings.current()
    return {"mcs_brand": current.brand, "mcs_title": current.title, "mcs_credit": current.credit,
            "mcs_show_generated_at": current.show_generated_at, "mcs_texture": current.texture,
            "mcs_width": current.width, "mcs_scale": current.scale, "mcs_min_height": current.min_height}


def normalize_startup(values):
    values = dict(values)
    values["mcs_width"] = settings.normalize_width(values["mcs_width"])
    values["mcs_scale"] = settings.normalize_scale(values["mcs_scale"])
    values["mcs_min_height"] = settings.normalize_min_height(values["mcs_min_height"])
    values["mcs_texture"] = str(values["mcs_texture"] or "").strip()
    return values


def base_startup():
    base = get_startup_base(settings.Config)
    if base is None:
        raise ConfigurationError("startup_base_unavailable", "启动环境配置尚未捕获")
    return normalize_startup(base.model_dump())


def startup_metadata():
    from .raster import list_textures
    choices = [{"value": "", "label": "按群稳定选择"}, {"value": "random", "label": "随机材质"},
               {"value": "none", "label": "不铺材质"}]
    choices.extend({"value": name, "label": name} for name in list_textures())
    return {"choices": {"mcs_texture": choices}, "readonly_fields": [], "notices": []}


def validate_startup(values):
    """完整候选中仅改变材质时检查存在性，资源移除不阻断其它字段修复。"""
    texture = values["mcs_texture"]
    previous = read_overrides().get("mcs_texture", base_startup()["mcs_texture"])
    if texture == str(previous or "").strip():
        return
    from .raster import list_textures
    if texture not in ("", "random", "none") and texture not in list_textures():
        raise ConfigurationError("invalid_config", "材质不存在", {"mcs_texture": "请选择已有材质"})


DECLARATION = declare_config(PluginConfiguration(
    key="mc_status", name="MC 服务器状态", feature_keys=("mc_status",),
    resources={"group": ConfigResource(MCGroup, read_group, write_group)},
    list_groups=dm.list_configured_groups,
    startup=StartupConfig(MCStartup, active_startup, base_startup, normalize_startup,
                          validate_startup, startup_metadata),
    migrate_legacy=dm.migrate_legacy_config,
))
