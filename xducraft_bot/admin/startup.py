"""Generic startup configuration resources; all field semantics are plugin-owned."""
from __future__ import annotations

from xducraft_bot.shared.configuration import (
    ConfigSnapshot, ConfigurationError, validate_values,
)
from xducraft_bot.shared.config_store import database


class StartupResources:
    def __init__(self, deployment):
        self.deployment = deployment

    @staticmethod
    def _startup(declaration):
        if declaration.startup is None:
            raise ConfigurationError("unknown_resource", "该插件没有声明启动参数")
        return declaration.startup

    def _overrides(self):
        try:
            return self.deployment.read_overrides()
        except self.deployment.DeploymentConfigError as exc:
            raise ConfigurationError(exc.code, "启动覆盖文件不可用，请修复文件后重试") from None

    def read(self, declaration) -> ConfigSnapshot:
        startup = self._startup(declaration)
        fields = set(startup.model.model_json_schema().get("properties", {}))
        stored = self._overrides()
        base = startup.base()
        pending = dict(base)
        pending.update({key: value for key, value in stored.items() if key in fields})
        pending = validate_values(startup.model, startup.normalize(pending))
        active = validate_values(startup.model, startup.normalize(startup.active()))
        defaults = validate_values(startup.model, startup.normalize(base))
        changed = sorted(key for key in fields if pending.get(key) != active.get(key))
        meta = dict(startup.metadata() if startup.metadata is not None else {})
        meta.update(active=active, defaults=defaults, overridden=sorted(fields.intersection(stored)),
                    restart_required=bool(changed), changed_keys=changed,
                    apply_status="active")
        if self.deployment.get_startup_failure() is not None:
            meta.setdefault("notices", []).append({"type": "warning", "message": "本进程启动时未应用覆盖文件；修复并保存后仍需重启"})
        return ConfigSnapshot(pending, meta, {"stored": {key: value for key, value in stored.items() if key in fields},
                                            "base": defaults, "active": active})

    def write(self, declaration, patch: dict) -> ConfigSnapshot:
        startup = self._startup(declaration)
        fields = set(startup.model.model_json_schema().get("properties", {}))
        if not isinstance(patch, dict) or set(patch) - {"set", "unset"}:
            raise ConfigurationError("invalid_config", "请使用字段设置与恢复环境值操作")
        changes, unset = patch.get("set", {}), patch.get("unset", [])
        if (not isinstance(changes, dict) or not isinstance(unset, list)
                or any(not isinstance(key, str) for key in unset)
                or set(changes) - fields or set(unset) - fields
                or len(set(unset)) != len(unset) or set(changes).intersection(unset)):
            raise ConfigurationError("invalid_config", "修改包含未知字段或重复操作")
        current = self.read(declaration)
        candidate = dict(current.values)
        candidate.update(changes)
        for key in unset:
            candidate[key] = current.meta["defaults"][key]
        candidate = validate_values(startup.model, candidate)
        candidate = validate_values(startup.model, startup.normalize(candidate))
        if startup.validate is not None:
            startup.validate(candidate)
        values = {key: candidate[key] for key in changes}
        try:
            self.deployment.update_overrides(values, unset)
        except self.deployment.DeploymentConfigError as exc:
            raise ConfigurationError(exc.code, "启动参数未能确认保存") from None
        db = database()
        with db.transaction() as connection:
            db.audit(connection, declaration.key, set(changes) | set(unset), "pending_restart", actor="web")
        return self.read(declaration)
