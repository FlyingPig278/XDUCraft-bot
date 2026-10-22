"""Opt-in runtime locations, independent of installed plugin code.

Set XDUCRAFT_DATA_DIR before starting NoneBot to use the external layout.
Without it, existing checkout deployments retain their exact legacy locations.
Path resolution never creates directories or imports NoneBot.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_KEY = re.compile(r"[A-Za-z0-9_-]+\Z")


class DataPathError(ValueError):
    """An explicit runtime location is unsafe or ambiguous."""


def runtime_data_root() -> Optional[Path]:
    raw = os.environ.get("XDUCRAFT_DATA_DIR")
    if raw is None:
        return None
    if not raw.strip():
        raise DataPathError("XDUCRAFT_DATA_DIR must be a non-empty absolute path")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise DataPathError("XDUCRAFT_DATA_DIR must be an absolute path")
    root = root.resolve()
    for child, parent in ((root, _PACKAGE_ROOT), (_PACKAGE_ROOT, root)):
        try:
            child.relative_to(parent)
        except ValueError:
            continue
        raise DataPathError("XDUCRAFT_DATA_DIR must not overlap the installed code package")
    return root


def _plugin_key(plugin_id: str) -> str:
    if not isinstance(plugin_id, str) or not _PLUGIN_KEY.fullmatch(plugin_id):
        raise DataPathError("plugin data locations require a stable configuration key")
    return plugin_id


def shared_data_dir() -> Path:
    root = runtime_data_root()
    return root / "core" if root is not None else Path(__file__).parent / "data"


def plugin_data_dir(plugin_id: str, legacy_dir: PathLike) -> Path:
    key = _plugin_key(plugin_id)
    root = runtime_data_root()
    return root / "plugins" / key if root is not None else Path(legacy_dir)


def plugin_cache_dir(plugin_id: str, legacy_dir: PathLike) -> Path:
    key = _plugin_key(plugin_id)
    root = runtime_data_root()
    return root / "cache" / key if root is not None else Path(legacy_dir)
