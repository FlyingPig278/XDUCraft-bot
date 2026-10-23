"""Runtime locations, independent of installed plugin code.

XDUCRAFT_DATA_DIR selects an explicit external layout. Without it, a unique
legacy shared/data location or flat source checkout preserves legacy paths;
new installations use the platform's user data directory. Resolution never
creates directories or imports NoneBot.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator, Optional, Union

import xducraft_bot
from platformdirs import user_data_path

PathLike = Union[str, Path]
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_KEY = re.compile(r"[A-Za-z0-9_-]+\Z")


class DataPathError(ValueError):
    """A runtime location is unsafe or ambiguous."""


def _namespace_roots() -> Iterator[Path]:
    """Ignore non-directory namespace entries, including editable finder hooks."""
    for entry in xducraft_bot.__path__:
        try:
            path = Path(entry)
            if not path.is_absolute():
                continue
            path = path.resolve()
            if path.is_dir():
                yield path
        except (OSError, RuntimeError, TypeError, ValueError):
            continue


def _legacy_namespace_root() -> Optional[Path]:
    candidates = set()
    for package in _namespace_roots():
        legacy = package / "shared" / "data"
        # A checkout using an external config DB may never create shared/data.
        if legacy.is_dir() or (
            package != _PACKAGE_ROOT
            and (package / "plugins").is_dir()
            and (package.parent / "pyproject.toml").is_file()
        ):
            candidates.add(package)
    if len(candidates) > 1:
        raise DataPathError(
            "Multiple legacy data layouts found; set XDUCRAFT_DATA_DIR explicitly"
        )
    return next(iter(candidates), None)


def _legacy_shared_data_dir() -> Optional[Path]:
    package = _legacy_namespace_root()
    return package / "shared" / "data" if package is not None else None


def runtime_data_root() -> Optional[Path]:
    raw = os.environ.get("XDUCRAFT_DATA_DIR")
    if raw is None:
        if _legacy_shared_data_dir() is not None:
            return None
        root = user_data_path("xducraft", appauthor=False).expanduser()
    else:
        if not raw.strip():
            raise DataPathError("XDUCRAFT_DATA_DIR must be a non-empty absolute path")
        root = Path(raw).expanduser()
    if not root.is_absolute():
        raise DataPathError("Runtime data directory must be an absolute path")
    root = root.resolve()
    for package in {_PACKAGE_ROOT, *_namespace_roots()}:
        for child, parent in ((root, package), (package, root)):
            try:
                child.relative_to(parent)
            except ValueError:
                continue
            raise DataPathError("Runtime data directory must not overlap an installed code package")
    return root


def _plugin_key(plugin_id: str) -> str:
    if not isinstance(plugin_id, str) or not _PLUGIN_KEY.fullmatch(plugin_id):
        raise DataPathError("plugin data locations require a stable configuration key")
    return plugin_id


def shared_data_dir() -> Path:
    root = runtime_data_root()
    if root is not None:
        return root / "core"
    legacy = _legacy_shared_data_dir()
    if legacy is None:
        raise DataPathError("Legacy shared/data directory disappeared during path resolution")
    return legacy




def _legacy_plugin_dir(
    legacy_dir: PathLike, legacy_relative_path: Optional[PathLike],
) -> Path:
    if legacy_relative_path is None:
        return Path(legacy_dir)
    relative = Path(legacy_relative_path)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise DataPathError("legacy plugin path must be a safe relative path")
    package = _legacy_namespace_root()
    if package is None:
        return Path(legacy_dir)
    candidate = (package.parent / relative).resolve()
    try:
        candidate.relative_to(package.parent)
    except ValueError:
        raise DataPathError("legacy plugin path must remain inside its source host") from None
    return candidate


def plugin_data_dir(
    plugin_id: str, legacy_dir: PathLike, *, legacy_relative_path: Optional[PathLike] = None,
) -> Path:
    key = _plugin_key(plugin_id)
    root = runtime_data_root()
    return root / "plugins" / key if root is not None else _legacy_plugin_dir(
        legacy_dir, legacy_relative_path,
    )


def plugin_cache_dir(
    plugin_id: str, legacy_dir: PathLike, *, legacy_relative_path: Optional[PathLike] = None,
) -> Path:
    key = _plugin_key(plugin_id)
    root = runtime_data_root()
    return root / "cache" / key if root is not None else _legacy_plugin_dir(
        legacy_dir, legacy_relative_path,
    )
