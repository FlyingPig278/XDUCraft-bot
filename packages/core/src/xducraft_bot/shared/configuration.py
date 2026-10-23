"""Plugin-owned configuration declarations; no WebUI or business-plugin imports."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, SecretBytes, SecretStr, TypeAdapter, ValidationError

PROTOCOL_KEY = "configuration"


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfigurationError(Exception):
    def __init__(self, code: str, message: str, fields: Optional[dict] = None):
        self.code, self.message, self.fields = code, message, fields or {}
        super().__init__(code)


@dataclass(frozen=True)
class ConfigContext:
    group_id: Optional[int] = None
    signature_key: bytes = field(default=b"", repr=False)
    actor: str = "plugin"
    check_current: Optional[Callable[[ConfigSnapshot], None]] = field(default=None, repr=False, compare=False)

    @property
    def scope(self) -> str:
        return "global" if self.group_id is None else "group"


@dataclass
class ConfigSnapshot:
    values: Dict[str, Any]
    meta: Dict[str, Any] = field(default_factory=dict)
    revision_data: Any = None

    @property
    def revision_values(self):
        return self.values if self.revision_data is None else self.revision_data


@dataclass(frozen=True)
class ConfigResource:
    model: Type[BaseModel]
    read: Callable[[ConfigContext], ConfigSnapshot]
    write: Callable[[ConfigContext, Dict[str, Any]], Any]
    write_mode: str = "replace"

    def json_schema(self) -> dict:
        schema = self.model.model_json_schema()
        return safe_schema(schema)


@dataclass(frozen=True)
class StartupConfig:
    model: Type[BaseModel]
    active: Callable[[], Dict[str, Any]]
    base: Callable[[], Dict[str, Any]]
    normalize: Callable[[Dict[str, Any]], Dict[str, Any]]
    validate: Optional[Callable[[Dict[str, Any]], None]] = None
    metadata: Optional[Callable[[], Dict[str, Any]]] = None


@dataclass(frozen=True)
class PluginConfiguration:
    key: str
    name: str
    resources: Mapping[str, ConfigResource] = field(default_factory=dict)
    feature_keys: Tuple[str, ...] = ()
    list_groups: Optional[Callable[[], Iterable[int]]] = None
    startup: Optional[StartupConfig] = None
    status: Optional[Callable[[ConfigContext], Dict[str, Any]]] = None
    media: Optional[Callable[[], Any]] = None
    managed: bool = True
    migrate_legacy: Optional[Callable[[], Any]] = None


_registry: Dict[str, PluginConfiguration] = {}
_native: Dict[str, Any] = {}


def declare_config(declaration: PluginConfiguration) -> PluginConfiguration:
    if declaration.key in _registry and _registry[declaration.key] is not declaration:
        raise ValueError("duplicate configuration declaration: " + declaration.key)
    if not declaration.key or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in declaration.key):
        raise ValueError("invalid configuration key")
    if set(declaration.resources) - {"global", "group"}:
        raise ValueError("only global and group configuration scopes are supported")
    if declaration.migrate_legacy is not None and not callable(declaration.migrate_legacy):
        raise ValueError("legacy migration callback must be callable")
    _registry[declaration.key] = declaration
    return declaration


async def migrate_legacy_configurations() -> Tuple[str, ...]:
    """Run each declared, idempotent legacy import after all plugins load.

    Callbacks must only establish their own active configuration document.  A
    failure aborts startup instead of replacing unreadable historical values
    with defaults.
    """
    completed = []
    for key in sorted(_registry):
        callback = _registry[key].migrate_legacy
        if callback is None:
            continue
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(
                "legacy_migration_failed",
                f"插件 {key} 的历史配置迁移失败",
            ) from exc
        completed.append(key)
    return tuple(completed)


def register_config(plugin_id: str, model: Type[BaseModel], *, scopes=("global", "group"),
                    on_change=None, name: Optional[str] = None,
                    feature_keys: Tuple[str, ...] = ()) -> PluginConfiguration:
    """Register a native SQLite-backed model without any WebUI dependency."""
    from .native_config import NativeConfiguration
    native = NativeConfiguration(plugin_id, model, scopes, on_change)
    declaration = PluginConfiguration(plugin_id, name or plugin_id, native.resources(),
                                      feature_keys, native.list_groups)
    declare_config(declaration)
    _native[plugin_id] = native
    return declaration


def get_declaration(plugin_id: str) -> PluginConfiguration:
    try:
        return _registry[plugin_id]
    except KeyError:
        raise ConfigurationError("unknown_plugin", "插件没有声明配置管理协议") from None


def get_config(plugin_id: str, scope: str = "global", scope_id: Optional[int] = None) -> BaseModel:
    if plugin_id in _native:
        return _native[plugin_id].get_config(scope, scope_id)
    declaration = get_declaration(plugin_id)
    context = scope_context(scope, scope_id)
    resource = declaration.resources.get(scope)
    if resource is None:
        raise ConfigurationError("unknown_resource", "此作用域没有该配置")
    snapshot = resource.read(context)
    return resource.model.model_validate(snapshot.meta.get("effective", snapshot.values))


async def update_config(plugin_id: str, values: dict, scope: str = "global", scope_id: Optional[int] = None,
                        *, actor: str = "plugin") -> ConfigSnapshot:
    declaration = get_declaration(plugin_id)
    context = scope_context(scope, scope_id, actor=actor)
    resource = declaration.resources.get(scope)
    if resource is None:
        raise ConfigurationError("unknown_resource", "此作用域没有该配置")
    candidate = values if resource.write_mode == "patch" else validate_values(resource.model, values)
    result = resource.write(context, candidate)
    if inspect.isawaitable(result):
        await result
    return resource.read(context)


def scope_context(scope: str, scope_id: Optional[int], *, actor: str = "plugin") -> ConfigContext:
    if scope == "global" and scope_id is None:
        return ConfigContext(actor=actor)
    if scope == "group" and type(scope_id) is int and scope_id > 0:
        return ConfigContext(scope_id, actor=actor)
    raise ConfigurationError("invalid_scope", "全局配置不带 ID；群配置需要正整数群号")


def validate_values(model: Type[BaseModel], values: dict) -> dict:
    try:
        result = private_json(model.model_validate(values))
        json.dumps(result, allow_nan=False)
        return result
    except ValidationError as exc:
        fields = {".".join(map(str, error["loc"])): "字段值或类型不合法"
                  for error in exc.errors(include_input=False, include_url=False, include_context=False)}
        raise ConfigurationError("invalid_config", "请修正标记的字段", fields) from None
    except (ValueError, TypeError, UnicodeError):
        raise ConfigurationError("invalid_config", "配置必须可表示为标准 JSON") from None


def private_json(value: Any) -> Any:
    """Persistence serialization must not accidentally save SecretStr's mask."""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, SecretBytes):
        return value.get_secret_value().decode("utf-8")
    if isinstance(value, BaseModel):
        dumped = value.model_dump(mode="json", by_alias=True)
        for name, model_field in type(value).model_fields.items():
            field_value = getattr(value, name)
            if isinstance(field_value, (BaseModel, SecretStr, SecretBytes, dict, list, tuple)):
                dumped[model_field.serialization_alias or model_field.alias or name] = private_json(field_value)
        return dumped
    if isinstance(value, dict):
        return {key: private_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [private_json(item) for item in value]
    return TypeAdapter(Any).dump_python(value, mode="json")


def safe_schema(schema: dict) -> dict:
    result = json.loads(json.dumps(schema))
    def scrub(node):
        if isinstance(node, dict):
            if node.get("writeOnly") or node.get("x-ui-secret"):
                for key in ("default", "examples", "enum", "const"):
                    node.pop(key, None)
            for value in node.values():
                scrub(value)
        elif isinstance(node, list):
            for value in node:
                scrub(value)
    scrub(result)
    return result


def discover_configurations(plugins: Iterable[Any]) -> Dict[str, tuple]:
    """Only loaded plugin metadata is consulted; removed modules are not imported."""
    result = {}
    for plugin in sorted(plugins, key=lambda value: value.id_):
        metadata = plugin.metadata
        declaration = (metadata.extra or {}).get(PROTOCOL_KEY) if metadata is not None else None
        if declaration is not None and not isinstance(declaration, PluginConfiguration):
            raise ConfigurationError("invalid_declaration", "插件配置协议声明类型不合法")
        declaration = declaration or _registry.get(plugin.id_)
        key = declaration.key if declaration else plugin.id_
        if key in result:
            raise ConfigurationError("duplicate_declaration", "插件配置标识重复")
        result[key] = (plugin, declaration)
    return result


def owner_of_feature(feature_key: str) -> Optional[PluginConfiguration]:
    return next((declaration for declaration in _registry.values() if feature_key in declaration.feature_keys), None)


def plugin_control(plugin_id: str, group_id: Optional[int] = None) -> dict:
    declaration = get_declaration(plugin_id)
    if not declaration.managed:
        raise ConfigurationError("unsupported_control", "该插件未声明完整停用能力")
    from .config_store import database
    db = database()
    result = db.control(plugin_id, group_id)
    root_enabled = db.control(plugin_id)["enabled"]
    native = _native.get(plugin_id)
    ready = native.ready(group_id) if native is not None and (group_id is not None or "global" in native.scopes) else True
    result["global_enabled"] = root_enabled
    result["effective"] = root_enabled and result["enabled"] and ready
    result["ready"] = ready
    return result


def is_plugin_enabled(plugin_id: str, group_id: Optional[int] = None) -> bool:
    declaration = _registry.get(plugin_id)
    if declaration is None:
        return False
    if not declaration.managed:
        return True
    return bool(plugin_control(plugin_id, group_id)["effective"])


def set_plugin_enabled(plugin_id: str, enabled: bool, group_id: Optional[int] = None, *, actor="plugin") -> dict:
    declaration = get_declaration(plugin_id)
    if not declaration.managed:
        raise ConfigurationError("unsupported_control", "该插件未声明完整停用能力")
    if type(enabled) is not bool:
        raise ConfigurationError("invalid_config", "插件开关必须为布尔值")
    from .config_store import config_write_context, database
    with config_write_context(actor, group_id):
        database().set_control(plugin_id, group_id, enabled)
    return plugin_control(plugin_id, group_id)


async def recover_config(plugin_id: str, context: ConfigContext, *, rollback=False) -> ConfigSnapshot:
    if plugin_id not in _native:
        raise ConfigurationError("unsupported_recovery", "此资源不使用框架应用回调")
    return await _native[plugin_id].recover(context, rollback=rollback)
