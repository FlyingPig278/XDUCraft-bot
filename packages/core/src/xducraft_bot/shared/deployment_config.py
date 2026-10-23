"""Validated deployment overrides applied once during process startup.

Deployment overrides are active only in Core SQLite.  A former JSON override
file is accepted once as an import input; removing a persisted key restores the
value captured from the process environment on the next restart.
"""

from __future__ import annotations

import json
from copy import deepcopy
from threading import RLock

from typing import Any, Dict, List, Mapping, Optional, Type, TypeVar
from nonebot.compat import model_dump, type_validate_python
from pydantic import BaseModel
from .config_store import ConfigDocumentStore
from .data_paths import shared_data_dir

T = TypeVar("T", bound=BaseModel)

DEPLOYMENT_CONFIG_INVALID = "deployment_config_invalid"
DEPLOYMENT_CONFIG_WRITE_FAILED = "deployment_config_write_failed"


DEPLOYMENT_OVERRIDES_PATH = shared_data_dir().resolve() / "deployment_overrides.json"


class DeploymentConfigError(RuntimeError):
    """A fixed, value-free deployment configuration error."""

    def __init__(self, code: str = DEPLOYMENT_CONFIG_INVALID) -> None:
        self.code = code
        super().__init__(code)


_LOCK = RLock()
_STARTUP_READY = False
_STARTUP_OVERRIDES: Dict[str, Any] = {}
_STARTUP_ERROR: Optional[str] = None
_STARTUP_BASES: Dict[Type[BaseModel], BaseModel] = {}


def _invalid() -> DeploymentConfigError:
    return DeploymentConfigError(DEPLOYMENT_CONFIG_INVALID)


def _validate_overrides(raw: Any) -> Dict[str, Any]:
    """Validate document structure; field semantics belong to plugin schemas.

    Unknown persisted fields are retained for temporarily unloaded plugins.
    Only a discovered declaration may authorize a WebUI write to those fields.
    """
    if not isinstance(raw, dict) or any(not isinstance(key, str) or not key for key in raw):
        raise _invalid()
    try:
        json.dumps(raw, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise _invalid() from None
    return deepcopy(raw)


_STORE = ConfigDocumentStore(
    "deployment_overrides",
    dict,
    _validate_overrides,
    legacy_path=str(DEPLOYMENT_OVERRIDES_PATH),
)


def read_overrides() -> Dict[str, Any]:
    """Read persisted next-start values from the unified configuration DB."""
    with _LOCK:
        try:
            return deepcopy(_STORE.load())
        except DeploymentConfigError:
            raise
        except Exception:
            raise _invalid() from None


def migrate_legacy_overrides() -> Dict[str, Any]:
    """Import the old deployment JSON exactly once into Core SQLite."""
    return read_overrides()


def update_overrides(values: Dict[str, Any], unset: List[str]) -> Dict[str, Any]:
    """Atomically apply sparse set/unset changes and return stored overrides."""

    if not isinstance(values, dict) or not isinstance(unset, list):
        raise _invalid()
    if any(not isinstance(key, str) or not key for key in unset):
        raise _invalid()
    if len(set(unset)) != len(unset) or set(values).intersection(unset):
        raise _invalid()

    validated_values = _validate_overrides(values)

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        updated = dict(_validate_overrides(current))
        updated.update(validated_values)
        for key in unset:
            updated.pop(key, None)
        updated = _validate_overrides(updated)
        current.clear()
        current.update(updated)
        return deepcopy(updated)

    with _LOCK:
        try:
            return _STORE.mutate(mutate)
        except DeploymentConfigError:
            raise
        except Exception:
            raise DeploymentConfigError(DEPLOYMENT_CONFIG_WRITE_FAILED) from None


def _copy_model(config: T) -> T:
    try:
        return type_validate_python(type(config), model_dump(config))
    except Exception:
        raise _invalid() from None


def _initialize_startup_snapshot() -> None:
    global _STARTUP_READY, _STARTUP_OVERRIDES, _STARTUP_ERROR
    if _STARTUP_READY:
        if _STARTUP_ERROR is not None:
            raise DeploymentConfigError(_STARTUP_ERROR)
        return

    try:
        overrides = read_overrides()
    except DeploymentConfigError as exc:
        _STARTUP_OVERRIDES = {}
        _STARTUP_ERROR = exc.code
        _STARTUP_READY = True
        raise DeploymentConfigError(exc.code) from None

    _STARTUP_OVERRIDES = deepcopy(overrides)
    _STARTUP_ERROR = None
    _STARTUP_READY = True


def apply_startup_overrides(config: T) -> T:
    """Merge the process-start override snapshot into a Pydantic config model.

    The first base model for each concrete config type is retained.  Repeated
    calls therefore cannot pick up later environment or file changes; only a
    new process applies newly saved deployment values.
    """

    if not isinstance(config, BaseModel):
        raise _invalid()

    config_type: Type[T] = type(config)
    with _LOCK:
        if config_type not in _STARTUP_BASES:
            _STARTUP_BASES[config_type] = _copy_model(config)
        _initialize_startup_snapshot()

        base = _STARTUP_BASES[config_type]
        merged = model_dump(base)
        for key, value in _STARTUP_OVERRIDES.items():
            if key in merged:
                merged[key] = deepcopy(value)
        try:
            return type_validate_python(config_type, merged)
        except Exception:
            raise _invalid() from None


def get_startup_base(config_type: Type[T]) -> Optional[T]:
    """Return an independent copy of the initially captured base model."""

    with _LOCK:
        base = _STARTUP_BASES.get(config_type)
        if base is None:
            return None
        try:
            return type_validate_python(config_type, model_dump(base))
        except Exception:
            raise _invalid() from None


def get_startup_failure() -> Optional[str]:
    """Return the fixed startup override error code, if startup validation failed."""

    with _LOCK:
        return _STARTUP_ERROR


def get_startup_overrides() -> Mapping[str, Any]:
    """Return a copy of the immutable process-start override snapshot."""

    with _LOCK:
        return deepcopy(_STARTUP_OVERRIDES)


__all__ = [
    "DEPLOYMENT_CONFIG_INVALID",
    "DEPLOYMENT_CONFIG_WRITE_FAILED",
    "DEPLOYMENT_OVERRIDES_PATH",
    "DeploymentConfigError",
    "apply_startup_overrides",
    "get_startup_base",
    "get_startup_failure",
    "get_startup_overrides",
    "migrate_legacy_overrides",
    "read_overrides",
    "update_overrides",
]
