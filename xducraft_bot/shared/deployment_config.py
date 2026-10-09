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
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type, TypeVar
from urllib.parse import urlsplit

from nonebot.compat import model_dump, type_validate_python
from pydantic import BaseModel

from .json_store import JsonStore

T = TypeVar("T", bound=BaseModel)

DEPLOYMENT_CONFIG_INVALID = "deployment_config_invalid"
DEPLOYMENT_CONFIG_WRITE_FAILED = "deployment_config_write_failed"

DEPLOYMENT_OVERRIDE_KEYS: Tuple[str, ...] = (
    "mcs_brand",
    "mcs_title",
    "mcs_credit",
    "mcs_show_generated_at",
    "mcs_texture",
    "mcs_width",
    "mcs_scale",
    "mcs_min_height",
    "invite_group_id",
    "invite_api_url",
    "invite_api_secret",
    "auto_accept_friend_group_ids",
)
ALLOWED_KEYS = frozenset(DEPLOYMENT_OVERRIDE_KEYS)

DEPLOYMENT_OVERRIDES_PATH = (
    Path(__file__).resolve().parent / "data" / "deployment_overrides.json"
)


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


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_https_url(value: str) -> str:
    normalized = value.strip()
    if not normalized or any(character.isspace() for character in normalized):
        raise _invalid()
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except (TypeError, ValueError):
        raise _invalid() from None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise _invalid()
    if port is not None and not 1 <= port <= 65535:
        raise _invalid()
    return normalized


def _validate_texture(value: str) -> str:
    normalized = value.strip()
    if normalized in {"", "random", "none"}:
        return normalized
    if (
        "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
        or Path(normalized).name != normalized
        or not normalized.lower().endswith(".png")
        or normalized in {".png", "..png"}
    ):
        raise _invalid()
    return normalized


def _validate_overrides(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise _invalid()
    if any(not isinstance(key, str) or key not in ALLOWED_KEYS for key in raw):
        raise _invalid()

    validated: Dict[str, Any] = {}
    for key, value in raw.items():
        if key in {"mcs_brand", "mcs_title", "mcs_credit", "invite_api_secret"}:
            if not isinstance(value, str):
                raise _invalid()
            validated[key] = value
        elif key == "mcs_texture":
            if not isinstance(value, str):
                raise _invalid()
            validated[key] = _validate_texture(value)
        elif key == "invite_api_url":
            if not isinstance(value, str):
                raise _invalid()
            validated[key] = _validate_https_url(value)
        elif key == "mcs_show_generated_at":
            if not isinstance(value, bool):
                raise _invalid()
            validated[key] = value
        elif key == "mcs_width":
            if not _is_plain_int(value) or not 480 <= value <= 1600:
                raise _invalid()
            validated[key] = value
        elif key == "mcs_scale":
            if not _is_plain_int(value) or value not in {2, 4}:
                raise _invalid()
            validated[key] = value
        elif key == "mcs_min_height":
            if not _is_plain_int(value) or value < 0:
                raise _invalid()
            validated[key] = value
        elif key == "invite_group_id":
            if not _is_plain_int(value) or value < 0:
                raise _invalid()
            validated[key] = value
        elif key == "auto_accept_friend_group_ids":
            if not isinstance(value, list):
                raise _invalid()
            group_ids: List[int] = []
            seen = set()
            for group_id in value:
                if not _is_plain_int(group_id) or group_id <= 0:
                    raise _invalid()
                if group_id not in seen:
                    seen.add(group_id)
                    group_ids.append(group_id)
            validated[key] = group_ids
        else:  # Kept as a guard if the allowlist and validator drift apart.
            raise _invalid()
    return validated


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
    if any(not isinstance(key, str) or key not in ALLOWED_KEYS for key in unset):
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
    "ALLOWED_KEYS",
    "DEPLOYMENT_CONFIG_INVALID",
    "DEPLOYMENT_CONFIG_WRITE_FAILED",
    "DEPLOYMENT_OVERRIDE_KEYS",
    "DEPLOYMENT_OVERRIDES_PATH",
    "DeploymentConfigError",
    "apply_startup_overrides",
    "get_startup_base",
    "get_startup_failure",
    "get_startup_overrides",
    "read_overrides",
    "update_overrides",
]
