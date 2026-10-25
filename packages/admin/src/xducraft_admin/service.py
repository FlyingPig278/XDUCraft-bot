"""Declaration-driven administration resources on the bot event loop."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import re
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from pydantic import ValidationError

from xducraft_bot.shared import configuration
from xducraft_bot.shared.configuration import (
    ConfigContext,
    ConfigSnapshot,
    ConfigurationError,
    PluginConfiguration,
    private_json,
    safe_schema,
    validate_values,
)
from xducraft_bot.shared.config_store import config_write_context, database

from . import models
from .adapters import CatalogPlugin

_MISSING = object()
_OMIT = object()
_SECRET_META_KEYS = {"defaults", "effective", "active", "applied", "pending"}

_BOT_INFO_TIMEOUT_SECONDS = 5


class AdminError(Exception):
    def __init__(self, status: int, code: str, message: str = "操作失败", fields: Optional[dict] = None):
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}
        super().__init__(code)


def _configuration_error(exc: ConfigurationError, *, reading: bool = False) -> AdminError:
    code = exc.code if isinstance(exc.code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", exc.code) else "configuration_error"
    if code.startswith("unknown_"):
        status, message = 404, "资源不存在"
    elif code.endswith("_unavailable") or (reading and code in {"deployment_config_invalid", "invalid_config"}):
        status, message = 503, "资源暂不可用"
    elif code == "storage_failed" or code.endswith("_write_failed"):
        status, message = 500, "配置未能确认保存"
    elif code.startswith(("invalid_", "schema_", "unsafe_")) or code.endswith("_invalid"):
        status, message = 422, "请修正标记的字段"
    else:
        status, message = 409, "当前状态不允许此操作"
    fields = {
        str(key): "字段值或状态不合法"
        for key in exc.fields
        if isinstance(key, (str, int)) and re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", str(key))
    }
    return AdminError(status, code, message, fields)


def _validate(model, data):
    try:
        return private_json(model.model_validate(data))
    except ValidationError as exc:
        fields = {
            ".".join(map(str, item["loc"])): "字段值或类型不合法"
            for item in exc.errors(include_input=False, include_url=False, include_context=False)
        }
        raise AdminError(422, "invalid_config", "请修正标记的字段", fields) from None


def _resolve(root: dict, node: Any) -> dict:
    if not isinstance(node, dict):
        return {}
    seen = set()
    current = node
    while isinstance(current, dict) and "$ref" in current:
        reference = current.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/") or reference in seen:
            break
        seen.add(reference)
        target: Any = root
        try:
            for part in reference[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            break
        if not isinstance(target, dict):
            break
        current = {**target, **{key: value for key, value in current.items() if key != "$ref"}}
    return current if isinstance(current, dict) else {}


def _matches_schema(root: dict, schema: dict, value: Any) -> bool:
    schema = _resolve(root, schema)
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    kind = schema.get("type")
    if isinstance(kind, list):
        return any(_matches_schema(root, {**schema, "type": item}, value) for item in kind)
    return (
        kind is None
        or (kind == "object" and isinstance(value, dict))
        or (kind == "array" and isinstance(value, list))
        or (kind == "string" and isinstance(value, str))
        or (kind == "boolean" and type(value) is bool)
        or (kind == "integer" and type(value) is int)
        or (kind == "number" and type(value) in (int, float))
        or (kind == "null" and value is None)
    )


def _branches(root: dict, schema: dict, value: Any) -> list[dict]:
    schema = _resolve(root, schema)
    result = [schema]
    for keyword in ("allOf", "oneOf", "anyOf"):
        options = schema.get(keyword)
        if not isinstance(options, list):
            continue
        matching = [_resolve(root, item) for item in options if _matches_schema(root, item, value)]
        if keyword == "allOf":
            result.extend(_resolve(root, item) for item in options)
        elif matching:
            result.extend(matching)
        else:
            result.extend(_resolve(root, item) for item in options)
    return result


def _is_secret(root: dict, schema: dict) -> bool:
    schema = _resolve(root, schema)
    if schema.get("writeOnly") or schema.get("x-ui-secret"):
        return True
    return any(
        isinstance(options, list) and any(_is_secret(root, item) for item in options)
        for key, options in schema.items()
        if key in ("allOf", "oneOf", "anyOf")
    )


def _has_secret(root: dict, schema: dict, seen: Optional[set[str]] = None) -> bool:
    if not isinstance(schema, dict):
        return False
    seen = set() if seen is None else set(seen)
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if reference in seen:
            return False
        seen.add(reference)
    schema = _resolve(root, schema)
    if _is_secret(root, schema):
        return True
    for branch in _branches(root, schema, None):
        properties = branch.get("properties", {})
        if isinstance(properties, dict) and any(_has_secret(root, item, seen) for item in properties.values()):
            return True
        items = branch.get("items")
        if isinstance(items, dict) and _has_secret(root, items, seen):
            return True
    return False


def _configured(value: Any) -> bool:
    value = private_json(value)
    return value is not None and value != "" and value != [] and value != {}


def _redact(root: dict, schema: dict, value: Any, path: str, fields: dict[str, bool]) -> Any:
    schema = _resolve(root, schema)
    if _is_secret(root, schema):
        if path:
            fields[path] = _configured(value)
        return _OMIT
    if isinstance(value, dict):
        properties: dict[str, Any] = {}
        additional: Any = None
        for branch in _branches(root, schema, value):
            if isinstance(branch.get("properties"), dict):
                properties.update(branch["properties"])
            if isinstance(branch.get("additionalProperties"), dict):
                additional = branch["additionalProperties"]
        result = {}
        for key, item in value.items():
            child_schema = properties.get(key, additional or {})
            child_path = f"{path}.{key}" if path else str(key)
            redacted = _redact(root, child_schema, item, child_path, fields)
            if redacted is not _OMIT:
                result[key] = redacted
        return result
    if isinstance(value, (list, tuple)):
        item_schema = next(
            (branch["items"] for branch in _branches(root, schema, value) if isinstance(branch.get("items"), dict)),
            {},
        )
        result = []
        for index, item in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            redacted = _redact(root, item_schema, item, child_path, fields)
            result.append(None if redacted is _OMIT else redacted)
        return result
    return private_json(value)


def _public_snapshot(schema: dict, snapshot: ConfigSnapshot) -> tuple[dict, dict]:
    secret_fields: dict[str, bool] = {}
    values = _redact(schema, schema, snapshot.values, "", secret_fields)
    public_meta = deepcopy(snapshot.meta)
    for key in _SECRET_META_KEYS:
        if key in public_meta:
            public_meta[key] = _redact(schema, schema, public_meta[key], "", {})
    existing = public_meta.get("secret_fields")
    if isinstance(existing, dict):
        secret_fields.update({str(key): bool(value) for key, value in existing.items()})
    public_meta["secret_fields"] = secret_fields
    return values if isinstance(values, dict) else {}, private_json(public_meta)


def _missing_secret(root: dict, schema: dict, value: Any) -> bool:
    schema = _resolve(root, schema)
    if _is_secret(root, schema):
        return value is _MISSING
    if isinstance(value, dict):
        properties = {}
        for branch in _branches(root, schema, value):
            if isinstance(branch.get("properties"), dict):
                properties.update(branch["properties"])
        return any(_missing_secret(root, child, value.get(key, _MISSING)) for key, child in properties.items() if _has_secret(root, child))
    if isinstance(value, list):
        item_schema = next((branch.get("items") for branch in _branches(root, schema, value) if isinstance(branch.get("items"), dict)), {})
        return any(_missing_secret(root, item_schema, item) for item in value)
    return False


def _public_for_compare(root: dict, schema: dict, value: Any) -> Any:
    return _redact(root, schema, value, "", {})


def _restore_secrets(root: dict, schema: dict, incoming: Any, current: Any, path: str = "") -> Any:
    schema = _resolve(root, schema)
    if _is_secret(root, schema):
        return deepcopy(current) if incoming is _MISSING else incoming
    if incoming is _MISSING:
        return deepcopy(current) if _has_secret(root, schema) else incoming
    if isinstance(incoming, dict):
        result = deepcopy(incoming)
        properties = {}
        for branch in _branches(root, schema, incoming):
            if isinstance(branch.get("properties"), dict):
                properties.update(branch["properties"])
        old = current if isinstance(current, dict) else {}
        for key, child_schema in properties.items():
            if not _has_secret(root, child_schema):
                continue
            restored = _restore_secrets(root, child_schema, incoming.get(key, _MISSING), old.get(key, _MISSING), f"{path}.{key}" if path else key)
            if restored is not _MISSING:
                result[key] = restored
        return result
    if isinstance(incoming, list):
        item_schema = next((branch.get("items") for branch in _branches(root, schema, incoming) if isinstance(branch.get("items"), dict)), {})
        if not _has_secret(root, item_schema):
            return incoming
        old = current if isinstance(current, list) else []
        label = schema.get("x-ui-label-field")
        if isinstance(label, str) and label and all(isinstance(item, dict) and label in item for item in incoming + old):
            old_by_key = {item[label]: item for item in old}
            if len(old_by_key) != len(old):
                raise ConfigurationError("unsafe_secret_reassignment", "含密钥的列表标识不唯一，请重新输入密钥")
            return [_restore_secrets(root, item_schema, item, old_by_key.get(item[label], _MISSING), f"{path}.{index}") for index, item in enumerate(incoming)]
        if any(_missing_secret(root, item_schema, item) for item in incoming):
            safe = len(incoming) == len(old) and all(
                _public_for_compare(root, item_schema, item) == _public_for_compare(root, item_schema, old[index])
                for index, item in enumerate(incoming)
            )
            if not safe:
                raise ConfigurationError("unsafe_secret_reassignment", "含密钥的列表改变顺序或内容时必须重新输入密钥")
        return [_restore_secrets(root, item_schema, item, old[index] if index < len(old) else _MISSING, f"{path}.{index}") for index, item in enumerate(incoming)]
    return incoming


class AdminService:
    def __init__(self, catalog, feature_gate, deployment, bots: Callable[[], Mapping[str, Any]], *, startup=None):
        self._catalog_source = catalog
        self.feature_gate = feature_gate
        self.deployment = deployment
        self.bots = bots
        if startup is None:
            from .startup import StartupResources
            startup = StartupResources(deployment)
        self.startup = startup
        self._revision_key = secrets.token_bytes(32)
        self._group_cache: Dict[str, list] = {}

    def catalog(self) -> Mapping[str, CatalogPlugin]:
        source = self._catalog_source() if callable(self._catalog_source) else self._catalog_source
        return dict(source)

    def revision(self, identity: Any, data: Any, schema: Optional[dict] = None) -> str:
        payload = private_json([identity, data, schema or {}])
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        return hmac.new(self._revision_key, raw, hashlib.sha256).hexdigest()

    def resource(self, identity: Any, config: dict, meta: Optional[dict] = None, raw: Any = None, schema: Optional[dict] = None):
        return {"config": config, "meta": meta or {}, "revision": self.revision(identity, config if raw is None else raw, schema)}

    @staticmethod
    def _expected(expected: Optional[str]) -> str:
        if expected is None:
            raise AdminError(428, "revision_required", "请先读取当前配置")
        if re.fullmatch(r"[a-f0-9]{64}", expected) is None:
            raise AdminError(400, "invalid_revision", "版本标识不合法")
        return expected

    def _check_snapshot(self, identity: Any, snapshot: ConfigSnapshot, schema: dict, expected: str) -> None:
        current = self.revision(identity, snapshot.revision_values, schema)
        if not hmac.compare_digest(current, expected):
            raise AdminError(409, "stale_config", "配置已被 QQ 或其他页面修改，请重新加载后再保存")

    def plugin(self, name: str, *, declared: bool = True) -> CatalogPlugin:
        entry = self.catalog().get(name)
        if entry is None:
            raise AdminError(404, "unknown_plugin", "不存在的插件")
        if not entry.loaded:
            raise AdminError(503, "plugin_unavailable", "插件未加载")
        if declared and entry.declaration is None:
            raise AdminError(404, "unknown_resource", "插件没有声明管理协议")
        return entry

    def _resource_parts(self, name: str, scope: str, gid: Optional[int] = None):
        entry = self.plugin(name)
        declaration = entry.declaration
        assert declaration is not None
        if scope == "startup":
            if declaration.startup is None or self.startup is None:
                raise AdminError(404, "unknown_resource", "此插件没有启动配置")
            schema = safe_schema(declaration.startup.model.model_json_schema())
            try:
                snapshot = self.startup.read(declaration)
            except ConfigurationError as exc:
                raise _configuration_error(exc, reading=True) from None
            return entry, declaration, None, schema, snapshot
        resource = declaration.resources.get(scope)
        if resource is None:
            raise AdminError(404, "unknown_resource", "此作用域没有该配置")
        context = ConfigContext(gid if scope == "group" else None, actor="web_admin")
        try:
            snapshot = resource.read(context)
        except ConfigurationError as exc:
            raise _configuration_error(exc, reading=True) from None
        return entry, declaration, (resource, context), resource.json_schema(), snapshot

    def get_config(self, name: str, gid: Optional[int] = None, *, scope: Optional[str] = None):
        scope = scope or ("group" if gid is not None else "global")
        _, _, _, schema, snapshot = self._resource_parts(name, scope, gid)
        config, meta = _public_snapshot(schema, snapshot)
        identity = ["config", name, scope, gid]
        return self.resource(identity, config, meta, snapshot.revision_values, schema)

    async def put_config(self, name: str, gid: Optional[int], data: dict, expected: Optional[str], *, scope: Optional[str] = None):
        scope = scope or ("group" if gid is not None else "global")
        expected_value = self._expected(expected)
        entry, declaration, parts, schema, snapshot = self._resource_parts(name, scope, gid)
        identity = ["config", name, scope, gid]
        self._check_snapshot(identity, snapshot, schema, expected_value)
        try:
            if scope == "startup":
                patch = _validate(models.Patch, data)
                changes = {}
                properties = schema.get("properties", {})
                for key, value in patch["set"].items():
                    child_schema = properties.get(key, {}) if isinstance(properties, dict) else {}
                    changes[key] = _restore_secrets(schema, child_schema, value, snapshot.values.get(key, _MISSING), key)
                patch["set"] = changes
                result = self.startup.write(declaration, patch)
                if inspect.isawaitable(result):
                    await result
            else:
                assert parts is not None
                resource, context = parts
                context = ConfigContext(
                    context.group_id,
                    actor="web_admin",
                    check_current=lambda current: self._check_snapshot(identity, current, schema, expected_value),
                )
                if resource.write_mode == "patch":
                    values = _validate(models.Patch, data)
                    properties = schema.get("properties", {})
                    values["set"] = {
                        key: _restore_secrets(schema, properties.get(key, {}) if isinstance(properties, dict) else {}, value, snapshot.values.get(key, _MISSING), key)
                        for key, value in values["set"].items()
                    }
                else:
                    restored = _restore_secrets(schema, schema, data, snapshot.values)
                    values = validate_values(resource.model, restored)
                with config_write_context("web_admin", context.group_id):
                    result = resource.write(context, values)
                    if inspect.isawaitable(result):
                        await result
        except ConfigurationError as exc:
            raise _configuration_error(exc) from None
        except ValidationError:
            raise AdminError(422, "invalid_config", "请修正标记的字段") from None
        except (TypeError, ValueError, UnicodeError):
            raise AdminError(422, "invalid_config", "配置内容不合法") from None
        return self.get_config(name, gid, scope=scope)

    async def recover_config(self, name: str, gid: Optional[int], expected: Optional[str], *, scope: Optional[str] = None, rollback: bool = False):
        scope = scope or ("group" if gid is not None else "global")
        if scope == "startup":
            raise AdminError(409, "unsupported_recovery", "启动配置通过重启生效")
        expected_value = self._expected(expected)
        _, declaration, parts, schema, snapshot = self._resource_parts(name, scope, gid)
        assert parts is not None
        identity = ["config", name, scope, gid]
        self._check_snapshot(identity, snapshot, schema, expected_value)
        context = ConfigContext(
            gid if scope == "group" else None,
            actor="web_admin",
            check_current=lambda current: self._check_snapshot(identity, current, schema, expected_value),
        )
        try:
            await configuration.recover_config(declaration.key, context, rollback=rollback)
        except ConfigurationError as exc:
            raise _configuration_error(exc) from None
        return self.get_config(name, gid, scope=scope)

    def _feature_owner(self, key: str) -> tuple[CatalogPlugin, PluginConfiguration, Any]:
        for entry in self.catalog().values():
            declaration = entry.declaration
            if declaration is not None and key in declaration.feature_keys:
                if not entry.loaded:
                    raise AdminError(503, "plugin_unavailable", "插件未加载")
                feature = self.feature_gate.get_feature(key)
                if feature is None:
                    raise AdminError(503, "feature_unavailable", "功能尚未注册")
                return entry, declaration, feature
        raise AdminError(404, "unknown_feature", "不存在的功能")

    def get_feature(self, key: str, gid: int):
        _, declaration, feature = self._feature_owner(key)
        enabled, source = self.feature_gate.resolve(key, gid)
        try:
            control = configuration.plugin_control(declaration.key, gid)
        except ConfigurationError as exc:
            raise _configuration_error(exc) from None
        owner_effective = True
        feature_state = self._status(declaration, gid).get("feature_effective", {})
        if isinstance(feature_state, dict):
            owner_effective = bool(feature_state.get(key, True))
        effective = bool(enabled and control["effective"] and owner_effective)
        meta = {
            "source": source,
            "resettable": False,
            "global_configurable": False,
            "superuser_only": bool(feature.superuser_only),
            "passive": bool(feature.passive),
            "effective": effective,
            "plugin_enabled": bool(control["effective"]),
            "global_enabled": bool(control["global_enabled"]),
            "ready": bool(control["ready"]),
        }
        raw = {"enabled": enabled, "source": source, "control": control.get("raw"), "owner_effective": owner_effective}
        return self.resource(["feature", key, gid], {"enabled": bool(enabled)}, meta, raw)

    def put_feature(self, key: str, gid: int, data: dict, expected: Optional[str]):
        current = self.get_feature(key, gid)
        expected_value = self._expected(expected)
        if not hmac.compare_digest(current["revision"], expected_value):
            raise AdminError(409, "stale_config", "配置已被 QQ 或其他页面修改，请重新加载后再保存")
        target = _validate(models.Switch, data)["enabled"]
        with config_write_context("web_admin", gid):
            self.feature_gate.set_enabled(key, gid, target)
        result = self.get_feature(key, gid)
        if result["config"]["enabled"] != target:
            raise AdminError(500, "storage_failed", "功能开关未能保存")
        return result

    def get_control(self, name: str, gid: Optional[int] = None):
        entry = self.plugin(name)
        declaration = entry.declaration
        assert declaration is not None
        if not declaration.managed:
            raise AdminError(409, "unsupported_control", "该插件未声明完整停用能力")
        try:
            state = configuration.plugin_control(declaration.key, gid)
        except ConfigurationError as exc:
            raise _configuration_error(exc) from None
        raw = state.pop("raw", None)
        explicit = raw[0] is not None if gid is None else raw[1] is not None
        effective = bool(state["effective"])
        if gid is not None and len(declaration.feature_keys) == 1:
            feature = self.get_feature(declaration.feature_keys[0], gid)
            effective = feature["meta"]["effective"]
            raw = {"control": raw, "feature_revision": feature["revision"]}
        meta = {
            "source": ("global" if gid is None else "group") if explicit else "default",
            "resettable": False,
            "effective": effective,
            "global_enabled": bool(state["global_enabled"]),
            "ready": bool(state["ready"]),
        }
        return self.resource(["control", name, gid], {"enabled": bool(state["enabled"])}, meta, raw)

    def put_control(self, name: str, gid: Optional[int], data: dict, expected: Optional[str]):
        current = self.get_control(name, gid)
        expected_value = self._expected(expected)
        if not hmac.compare_digest(current["revision"], expected_value):
            raise AdminError(409, "stale_config", "配置已被 QQ 或其他页面修改，请重新加载后再保存")
        entry = self.plugin(name)
        declaration = entry.declaration
        assert declaration is not None
        enabled = _validate(models.Switch, data)["enabled"]
        try:
            if gid is not None and len(declaration.feature_keys) == 1:
                with config_write_context("web_admin", gid):
                    self.feature_gate.set_enabled(declaration.feature_keys[0], gid, enabled)
            else:
                configuration.set_plugin_enabled(declaration.key, enabled, gid, actor="web_admin")
        except ConfigurationError as exc:
            raise _configuration_error(exc) from None
        result = self.get_control(name, gid)
        feature_matches = gid is None or len(declaration.feature_keys) != 1 or self.feature_gate.resolve(declaration.feature_keys[0], gid)[0] == enabled
        if result["config"]["enabled"] != enabled or not feature_matches:
            raise AdminError(500, "storage_failed", "插件开关未能保存")
        return result

    def _status(self, declaration: PluginConfiguration, gid: Optional[int]) -> dict:
        if declaration.status is None:
            return {"available": True, "reason": None, "notices": []}
        try:
            result = declaration.status(ConfigContext(gid, actor="web_admin"))
        except ConfigurationError as exc:
            sanitized = _configuration_error(exc, reading=True)
            return {"available": False, "reason": sanitized.message, "notices": []}
        return private_json(result)

    def _descriptor(self, entry: CatalogPlugin, gid: Optional[int]) -> dict:
        declaration = entry.declaration
        descriptor = {
            "id": entry.id,
            "short_name": entry.short_name,
            "name": entry.name,
            "loaded": bool(entry.loaded),
            "description": entry.description,
            "managed": bool(declaration is not None and declaration.managed),
            "group_config": False,
            "global_config": False,
            "resources": {},
            "features": [],
            "context": {"available": bool(entry.loaded), "reason": None if entry.loaded else "插件未加载", "notices": []},
        }
        if not entry.loaded or declaration is None:
            return descriptor
        descriptor["context"].update(self._status(declaration, gid))
        if "group" in declaration.resources:
            descriptor["group_config"] = True
            descriptor["resources"]["group"] = {
                "path": f"/api/groups/{gid}/config/{entry.short_name}" if gid is not None else "/api/groups/:gid/config/" + entry.short_name,
                "schema": declaration.resources["group"].json_schema(),
                "write_mode": declaration.resources["group"].write_mode,
                "scope": "group",
            }
        if "global" in declaration.resources:
            descriptor["global_config"] = True
            descriptor["resources"]["global"] = {
                "path": "/api/global/config/" + entry.short_name,
                "schema": declaration.resources["global"].json_schema(),
                "write_mode": declaration.resources["global"].write_mode,
                "scope": "global",
            }
        if declaration.startup is not None:
            descriptor["resources"]["startup"] = {
                "path": "/api/startup/config/" + entry.short_name,
                "schema": safe_schema(declaration.startup.model.model_json_schema()),
                "write_mode": "patch",
                "scope": "startup",
            }
        for key in declaration.feature_keys:
            try:
                if gid is None:
                    continue
                state = self.get_feature(key, gid)
                feature = self.feature_gate.get_feature(key)
                descriptor["features"].append({
                    "key": key,
                    "name": feature.name,
                    "description": feature.description,
                    **state["config"],
                    **state["meta"],
                    "revision": state["revision"],
                })
            except AdminError as exc:
                descriptor["context"]["available"] = False
                descriptor["context"]["reason"] = exc.message
        if declaration.managed:
            try:
                descriptor["control"] = self.get_control(entry.short_name, gid)
            except AdminError as exc:
                descriptor["context"]["notices"].append({"type": "warning", "message": exc.message})
        if declaration.media is not None:
            try:
                provider = declaration.media()
                descriptor["media"] = {
                    "upload_url": f"/api/plugins/{entry.short_name}/media",
                    "read_url_prefix": f"/api/plugins/{entry.short_name}/media/",
                    "max_bytes": int(provider.max_bytes),
                    "mime_types": list(provider.mime_types),
                }
            except Exception:
                descriptor["context"]["notices"].append({"type": "warning", "message": "媒体能力暂不可用"})
        return descriptor

    def plugins(self, gid: Optional[int] = None):
        return {"plugins": [self._descriptor(entry, gid) for _, entry in sorted(self.catalog().items())]}

    def media_provider(self, name: str):
        entry = self.plugin(name)
        declaration = entry.declaration
        assert declaration is not None
        if declaration.media is None:
            raise AdminError(404, "unknown_resource", "插件没有媒体能力")
        try:
            return declaration.media()
        except Exception:
            raise AdminError(503, "media_unavailable", "媒体能力暂不可用") from None

    async def upload_media(self, name: str, content: bytes):
        provider = self.media_provider(name)
        try:
            result = provider.upload(content)
            if inspect.isawaitable(result):
                result = await result
        except (ValueError, OSError):
            raise AdminError(415, "invalid_media", "媒体损坏或格式不支持") from None
        return {"name": str(result)}

    def resolve_media(self, name: str, asset: str) -> tuple[Path, str]:
        provider = self.media_provider(name)
        try:
            path, mime = provider.resolve(asset)
            return Path(path), str(mime)
        except (ValueError, OSError):
            raise AdminError(404, "media_not_found", "媒体不存在") from None

    async def overview(self):
        catalog = self.catalog()
        restart = False
        warning = None
        if self.startup is not None:
            for entry in catalog.values():
                if entry.declaration is None or entry.declaration.startup is None:
                    continue
                try:
                    snapshot = self.startup.read(entry.declaration)
                    restart = restart or bool(snapshot.meta.get("restart_required"))
                except ConfigurationError as exc:
                    warning = exc.code

        async def bot_overview(bot_id: str, bot: Any) -> dict:
            result = {"bot_id": bot_id, "connected": True}
            try:
                login_info = await asyncio.wait_for(
                    bot.get_login_info(),
                    _BOT_INFO_TIMEOUT_SECONDS,
                )
            except Exception:
                return result
            if isinstance(login_info, Mapping):
                nickname = login_info.get("nickname")
                if isinstance(nickname, str) and nickname.strip():
                    result["nickname"] = nickname
            return result

        bots = [
            (str(bot_id), bot)
            for bot_id, bot in self.bots().items()
        ]
        bot_rows = await asyncio.gather(*(
            bot_overview(bot_id, bot)
            for bot_id, bot in sorted(bots, key=lambda item: item[0])
        ))
        return {
            "bots": bot_rows,
            "plugins": [{"id": entry.id, "name": entry.name, "loaded": entry.loaded, "reason": None if entry.loaded else "插件未加载"} for entry in catalog.values()],
            "restart_required": restart,
            "deployment_warning": warning,
        }

    async def groups(self):
        bots = dict(self.bots())
        warnings = []
        successful = set()

        async def fetch(bot_id, bot):
            try:
                rows = await asyncio.wait_for(bot.get_group_list(), 5)
                cleaned = [{"group_id": models.positive_id(str(row["group_id"])), "group_name": str(row.get("group_name", ""))} for row in rows]
                self._group_cache[str(bot_id)] = cleaned
                successful.add(str(bot_id))
            except Exception:
                warnings.append("机器人 " + str(bot_id) + " 的群列表暂不可用，保留最近成功结果")

        await asyncio.gather(*(fetch(key, bots[key]) for key in sorted(bots)))
        known = set()
        try:
            known.update(self.feature_gate.list_configured_groups())
        except Exception:
            warnings.append("共享开关的已配置群列表不可用")
        try:
            known.update(database().list_control_groups())
        except Exception:
            warnings.append("插件总开关的已配置群列表不可用")
        for entry in self.catalog().values():
            declaration = entry.declaration
            if not entry.loaded or declaration is None or declaration.list_groups is None:
                continue
            try:
                known.update(declaration.list_groups())
            except Exception:
                warnings.append(entry.name + " 的已配置群列表不可用")
        entries = {}
        for bot_id in sorted(self._group_cache, key=lambda key: (key not in successful, key)):
            for row in self._group_cache[bot_id]:
                gid = row["group_id"]
                current = bot_id in successful
                entry = entries.setdefault(gid, {"group_id": str(gid), "name": row["group_name"] or "群 " + str(gid), "bot_ids": [], "connected": False, "stale": not current})
                entry["bot_ids"].append(bot_id)
                entry["connected"] |= current
                if current:
                    entry["stale"] = False
        for value in known:
            try:
                gid = int(value)
                if gid > 0:
                    entries.setdefault(gid, {"group_id": str(gid), "name": "群 " + str(gid), "bot_ids": [], "connected": False, "stale": False})
            except (ValueError, TypeError):
                continue
        return {"groups": [entries[gid] for gid in sorted(entries)], "warnings": sorted(warnings)}


__all__ = ["AdminError", "AdminService"]
