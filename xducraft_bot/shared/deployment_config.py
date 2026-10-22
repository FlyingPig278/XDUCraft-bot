"""Validated deployment overrides applied once during process startup.

The override file deliberately contains only explicit web-admin overrides.  It is
not a copy of NoneBot's environment configuration: removing a key restores the
value captured from the process environment on the next restart.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock

from typing import Any, Dict, List, Mapping, Optional, Type, TypeVar
from nonebot.compat import model_dump, type_validate_python
from pydantic import BaseModel

from .data_paths import shared_data_dir
from .json_store import JsonStore

T = TypeVar("T", bound=BaseModel)

DEPLOYMENT_CONFIG_INVALID = "deployment_config_invalid"
DEPLOYMENT_CONFIG_WRITE_FAILED = "deployment_config_write_failed"


DEPLOYMENT_OVERRIDES_PATH = shared_data_dir().resolve() / "deployment_overrides.json"


class DeploymentConfigError(RuntimeError):
    """A fixed, value-free deployment configuration error."""

    def __init__(self, code: str = DEPLOYMENT_CONFIG_INVALID) -> None:
        self.code = code
        super().__init__(code)


_STORE: JsonStore[Dict[str, Any]] = JsonStore(
    str(DEPLOYMENT_OVERRIDES_PATH), dict
)
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


def _store_path() -> Path:
    return Path(_STORE.path)


def _read_file_strict() -> Dict[str, Any]:
    try:
        with open(_store_path(), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise _invalid() from None
    return _validate_overrides(raw)


def read_overrides() -> Dict[str, Any]:
    """Read and fully validate the latest override file.

    A missing file is an empty override set.  Invalid or unreadable files are
    never treated as empty, rewritten, or cached as defaults.
    """

    with _LOCK:
        return deepcopy(_read_file_strict())


def _replace_store_data(data: Dict[str, Any]) -> None:
    def replace(current: Dict[str, Any]) -> None:
        if not isinstance(current, dict):
            raise _invalid()
        current.clear()
        current.update(deepcopy(data))

    try:
        _STORE.invalidate()
        _STORE.mutate(replace)
        if os.name != "nt":
            os.chmod(_store_path(), 0o600)
    except DeploymentConfigError:
        raise
    except Exception:
        raise DeploymentConfigError(DEPLOYMENT_CONFIG_WRITE_FAILED) from None


def update_overrides(values: Dict[str, Any], unset: List[str]) -> Dict[str, Any]:
    """Atomically apply sparse set/unset changes and return stored overrides."""

    if not isinstance(values, dict) or not isinstance(unset, list):
        raise _invalid()
    if any(not isinstance(key, str) or not key for key in unset):
        raise _invalid()
    if len(set(unset)) != len(unset) or set(values).intersection(unset):
        raise _invalid()

    validated_values = _validate_overrides(values)
    with _LOCK:
        current = _read_file_strict()
        updated = dict(current)
        updated.update(validated_values)
        for key in unset:
            updated.pop(key, None)
        updated = _validate_overrides(updated)
        _replace_store_data(updated)
        return deepcopy(updated)


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
        overrides = _read_file_strict()
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
    "read_overrides",
    "update_overrides",
]
