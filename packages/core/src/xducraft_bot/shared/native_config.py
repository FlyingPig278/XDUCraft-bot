"""Default model-backed global/group configuration and explicit apply recovery."""
from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy
from typing import Optional

from pydantic import ValidationError, create_model
from pydantic_core import PydanticUndefined

from .config_store import database
from .configuration import (
    ConfigContext, ConfigModel, ConfigResource, ConfigSnapshot,
    ConfigurationError, private_json, validate_values,
)


class NativeConfiguration:
    def __init__(self, plugin_id, model, scopes, on_change):
        self.plugin_id, self.model, self.scopes, self.on_change = plugin_id, model, tuple(scopes), on_change
        if not self.scopes or set(self.scopes) - {"global", "group"}:
            raise ValueError("native configuration supports global and group scopes only")
        self.properties = model.model_json_schema().get("properties", {})
        self.defaults = {}
        for name, model_field in model.model_fields.items():
            key = model_field.validation_alias or model_field.alias or name
            if not isinstance(key, str):
                raise ValueError("configuration fields need a single JSON property key")
            value = model_field.get_default(call_default_factory=True)
            if value is not PydanticUndefined:
                self.defaults[key] = private_json(value)
        self.startup_keys = {key for key, spec in self.properties.items() if spec.get("x-ui-effect-phase") == "startup"}
        for key in self.startup_keys:
            if self.properties[key].get("x-ui-scope", "global_only") != "global_only":
                raise ValueError("startup configuration is global-only")
        self.group_keys = self.allowed("group")
        self.global_keys = self.allowed("global")
        self.shared_keys = {
            key for key, spec in self.properties.items()
            if spec.get("x-ui-scope") == "global_only"
        }
        group_fields = {}
        for name, model_field in model.model_fields.items():
            key = model_field.validation_alias or model_field.alias or name
            if key in self.group_keys:
                group_fields[name] = (model_field.annotation, deepcopy(model_field))
        self.group_model = create_model(
            model.__name__ + "Group",
            __base__=ConfigModel,
            **group_fields,
        )
        database().prepare_native_groups(
            self.plugin_id, self.defaults, self.group_keys, self.properties,
        )
        self._lock = asyncio.Lock()
        self._updating_task = None
        root = database().read_values(plugin_id, "global")
        self._startup = {key: root["desired"].get(key, self.defaults.get(key)) for key in self.startup_keys}
        if self.startup_keys and root["revision"]:
            applied = dict(root["applied"])
            for key in self.startup_keys:
                if key in root["desired"]:
                    applied[key] = root["desired"][key]
                else:
                    applied.pop(key, None)
            if applied != root["applied"]:
                database().write_values(plugin_id, "global", None, desired=root["desired"], applied=applied,
                                        status=root["status"], error=root["error"], fields=self.startup_keys,
                                        actor="startup")

    def allowed(self, scope):
        return {key for key, spec in self.properties.items()
                if (scope == "global" and spec.get("x-ui-scope") != "group_only")
                or (scope == "group" and spec.get("x-ui-scope") != "global_only" and key not in self.startup_keys)}

    def _values(self, scope, scope_id, *, applied=False):
        db = database()
        if scope == "group":
            db.prepare_native_groups(
                self.plugin_id, self.defaults, self.group_keys, self.properties,
            )
            db.ensure_native_group(
                self.plugin_id,
                scope_id,
                {key: deepcopy(value) for key, value in self.defaults.items() if key in self.group_keys},
            )
        root = db.read_values(self.plugin_id, "global")
        row = db.read_values(self.plugin_id, scope, scope_id)
        slot = "applied" if applied else "desired"
        values = deepcopy({key: value for key, value in self.defaults.items() if key in self.properties})
        if scope == "global":
            values.update({key: value for key, value in root[slot].items() if key in self.properties})
        else:
            values.update({key: value for key, value in root["applied"].items() if key in self.shared_keys})
            values.update({key: value for key, value in row[slot].items() if key in self.group_keys})
        if applied:
            values.update(deepcopy(self._startup))
        return values, root, row

    def get_config(self, scope, scope_id):
        self._check_scope(scope, scope_id)
        values, _, _ = self._values(scope, scope_id, applied=True)
        try:
            return self.model.model_validate(values)
        except ValidationError:
            raise ConfigurationError("invalid_config", "插件的当前配置尚未通过校验") from None

    def _check_scope(self, scope, scope_id):
        if scope not in self.scopes:
            raise ConfigurationError("unknown_resource", "此作用域没有该配置")
        if scope == "global" and scope_id is not None:
            raise ConfigurationError("invalid_scope", "全局配置不带群号")
        if scope == "group" and (type(scope_id) is not int or scope_id <= 0):
            raise ConfigurationError("invalid_scope", "群配置需要正整数群号")

    def read(self, context):
        scope, scope_id = context.scope, context.group_id
        self._check_scope(scope, scope_id)
        desired, root, row = self._values(scope, scope_id)
        applied, _, _ = self._values(scope, scope_id, applied=True)
        if scope == "group":
            saved = {key: deepcopy(desired[key]) for key in self.group_keys if key in desired}
            defaults = {key: deepcopy(value) for key, value in self.defaults.items() if key in self.group_keys}
            published_applied = {key: deepcopy(applied[key]) for key in self.group_keys if key in applied}
        else:
            saved = desired
            defaults = deepcopy(self.defaults)
            published_applied = applied
        unknown = sorted(set(row["desired"]) - set(self.properties))
        invalid = []
        try:
            self.model.model_validate(desired)
        except ValidationError as exc:
            invalid = [".".join(map(str, error["loc"])) for error in exc.errors(include_input=False, include_url=False, include_context=False)]
        applied_invalid = []
        try:
            self.model.model_validate(applied)
        except ValidationError as exc:
            applied_invalid = [".".join(map(str, error["loc"])) for error in exc.errors(include_input=False, include_url=False, include_context=False)]
        root_blocks_scope = scope == "global"
        if scope == "group" and root["status"] != "active":
            missing = object()
            root_blocks_scope = any(
                root["desired"].get(key, missing) != root["applied"].get(key, missing)
                for key in self.shared_keys
            )
        status = root["status"] if root_blocks_scope and root["status"] != "active" else row["status"]
        if invalid or unknown or applied_invalid:
            status = "invalid"
        apply_error = root["error"] if root_blocks_scope and root["status"] != "active" else row["error"]
        return ConfigSnapshot(
            saved,
            {"defaults": defaults, "effective": published_applied, "applied": published_applied,
             **({"overridden": sorted(key for key in row["desired"] if key in self.global_keys)} if scope == "global" else {}),
             "apply_status": status, "apply_error": apply_error,
             "apply_scope": "global" if root_blocks_scope and root["status"] != "active" else scope,
             "invalid_fields": invalid, "applied_invalid_fields": applied_invalid, "orphaned_fields": unknown,
             "restart_required": any(desired.get(key) != applied.get(key) for key in self.startup_keys),
             "changed_startup_fields": sorted(key for key in self.startup_keys if desired.get(key) != applied.get(key))},
            {"local": row, "defaults": defaults},
        )

    def resources(self):
        resources = {}
        if "global" in self.scopes:
            resources["global"] = ConfigResource(self.model, self.read, self.write, "patch")
        if "group" in self.scopes:
            resources["group"] = ConfigResource(self.group_model, self.read, self.write, "replace")
        return resources

    def list_groups(self):
        return database().list_groups(self.plugin_id)

    def _effective_candidate(self, scope, candidate, root, *, root_slot="desired"):
        effective = deepcopy(self.defaults)
        if scope == "group":
            effective.update({
                key: value for key, value in root[root_slot].items()
                if key in self.shared_keys
            })
        effective.update(candidate)
        return validate_values(self.model, effective)

    async def write(self, context, payload):
        scope, scope_id = context.scope, context.group_id
        self._check_scope(scope, scope_id)
        if scope == "global":
            if not isinstance(payload, dict) or set(payload) - {"set", "unset"}:
                raise ConfigurationError("invalid_config", "配置修改需要 set/unset 对象")
            changes, unset = payload.get("set", {}), payload.get("unset", [])
            if (not isinstance(changes, dict) or not isinstance(unset, list)
                    or any(not isinstance(key, str) for key in unset)):
                raise ConfigurationError("invalid_config", "配置修改格式不合法")
            if set(changes) & set(unset):
                raise ConfigurationError("invalid_config", "同一字段不能同时设置和删除")
        else:
            changes = validate_values(self.group_model, payload)
            unset = []
        if self._updating_task is asyncio.current_task():
            raise ConfigurationError("recursive_config_update", "配置回调不能递归修改同一插件")
        async with self._lock:
            self._updating_task = asyncio.current_task()
            try:
                if context.check_current is not None:
                    context.check_current(self.read(context))
                _, root, old_row = self._values(scope, scope_id)
                if scope == "global":
                    allowed = self.allowed(scope)
                    removable = allowed | (set(old_row["desired"]) - set(self.properties))
                    if set(changes) - allowed or set(unset) - removable:
                        raise ConfigurationError("invalid_config", "字段不允许在当前作用域修改")
                    candidate = deepcopy(old_row["desired"])
                    candidate.update(changes)
                    for key in unset:
                        candidate.pop(key, None)
                    if set(candidate) - set(self.properties):
                        raise ConfigurationError("schema_changed", "请明确移除已停用的旧字段后再保存")
                else:
                    candidate = {key: deepcopy(value) for key, value in changes.items() if key in self.group_keys}
                validated = self._effective_candidate(
                    scope, candidate, root,
                    root_slot="applied" if scope == "group" else "desired",
                )
                candidate = {key: validated[key] for key in candidate}
                missing = object()
                changed_fields = {
                    key for key in set(candidate) | set(old_row["desired"])
                    if candidate.get(key, missing) != old_row["desired"].get(key, missing)
                }
                if not changed_fields and old_row["status"] == "active":
                    return
                new_applied = dict(candidate)
                if scope == "global":
                    for key in self.startup_keys:
                        if key in old_row["applied"]:
                            new_applied[key] = old_row["applied"][key]
                        else:
                            new_applied.pop(key, None)
                runtime_old = self._values(scope, scope_id, applied=True)[0]
                runtime_new = self._effective_candidate(
                    scope, candidate, root,
                    root_slot="applied" if scope == "group" else "desired",
                )
                runtime_new.update(deepcopy(self._startup))
                db = database()
                db.write_values(
                    self.plugin_id, scope, scope_id,
                    desired=candidate, applied=old_row["applied"],
                    status="applying", fields=changed_fields, actor=context.actor,
                )
                try:
                    await self._notify(context, runtime_old, runtime_new)
                except asyncio.CancelledError:
                    db.write_values(
                        self.plugin_id, scope, scope_id,
                        desired=candidate, applied=old_row["applied"],
                        status="failed", error="配置应用被取消",
                        fields=changed_fields, actor=context.actor,
                    )
                    raise
                except Exception as exc:
                    db.write_values(
                        self.plugin_id, scope, scope_id,
                        desired=candidate, applied=old_row["applied"],
                        status="failed", error="配置应用失败（" + type(exc).__name__ + "）",
                        fields=changed_fields, actor=context.actor,
                    )
                    return
                db.write_values(
                    self.plugin_id, scope, scope_id,
                    desired=candidate, applied=new_applied,
                    status="active", fields=changed_fields, actor=context.actor,
                )
            finally:
                self._updating_task = None

    async def _notify(self, context, old_values, new_values):
        if self.on_change is None:
            return
        try:
            old_model = self.model.model_validate(old_values)
        except ValidationError:
            old_model = None
        new_model = self.model.model_validate(new_values)
        result = self.on_change(context, old_model, new_model)
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=30)

    async def recover(self, context: ConfigContext, *, rollback=False):
        self._check_scope(context.scope, context.group_id)
        if self._updating_task is asyncio.current_task():
            raise ConfigurationError("recursive_config_update", "配置回调不能递归修改同一插件")
        async with self._lock:
            self._updating_task = asyncio.current_task()
            try:
                if context.check_current is not None:
                    context.check_current(self.read(context))
                db = database()
                row = db.read_values(self.plugin_id, context.scope, context.group_id)
                if row["status"] not in ("failed", "applying"):
                    raise ConfigurationError("apply_not_failed", "此配置没有待恢复的应用失败")
                target = row["applied"] if rollback else row["desired"]
                old_values = self._values(context.scope, context.group_id, applied=True)[0]
                _, root, _ = self._values(context.scope, context.group_id)
                desired = self._effective_candidate(
                    context.scope, target, root, root_slot="applied",
                )
                runtime_new = dict(desired)
                runtime_new.update(deepcopy(self._startup))
                try:
                    # Retry hooks run even if the previous attempt partially changed
                    # external state; plugin hooks must be idempotent.
                    if self.on_change is not None:
                        try:
                            old_model = self.model.model_validate(old_values)
                        except ValidationError:
                            old_model = None
                        result = self.on_change(context, old_model, self.model.model_validate(runtime_new))
                        if inspect.isawaitable(result):
                            await asyncio.wait_for(result, timeout=30)
                except asyncio.CancelledError:
                    db.write_values(self.plugin_id, context.scope, context.group_id, desired=row["desired"], applied=row["applied"],
                                    status="failed", error="配置恢复被取消", actor=context.actor)
                    raise
                except Exception as exc:
                    db.write_values(self.plugin_id, context.scope, context.group_id, desired=row["desired"], applied=row["applied"],
                                    status="failed", error="配置恢复失败（" + type(exc).__name__ + "）", actor=context.actor)
                    return self.read(context)
                applied = dict(target)
                for key in self.startup_keys:
                    if key in row["applied"]:
                        applied[key] = row["applied"][key]
                    else:
                        applied.pop(key, None)
                db.write_values(self.plugin_id, context.scope, context.group_id, desired=target, applied=applied,
                                status="active", fields=target, actor=context.actor)
                return self.read(context)
            finally:
                self._updating_task = None

    def ready(self, group_id: Optional[int] = None):
        scope = "group" if group_id is not None and "group" in self.scopes else "global"
        if scope not in self.scopes:
            scope = self.scopes[0]
        context = ConfigContext(group_id if scope == "group" else None)
        try:
            return self.read(context).meta["apply_status"] == "active"
        except ConfigurationError:
            return False
