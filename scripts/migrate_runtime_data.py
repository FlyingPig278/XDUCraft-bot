#!/usr/bin/env python3
"""Create and restore verified, offline XDUCraft runtime-data snapshots.

The source application MUST be stopped before this tool is run.  The tool does
not stop NoneBot and cannot prove that all writers are inactive; SQLite files
are transactionally backed up, but cross-database and database/media
consistency still requires an offline source.

Snapshots can contain unencrypted credentials from legacy JSON files.  File
modes are preserved where the platform supports them, but this tool does not
encrypt snapshots or claim to harden Windows ACLs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

PathLike = Union[str, os.PathLike]
MANIFEST_NAME = ".xducraft-runtime-data.json"
MANIFEST_FORMAT = "xducraft-runtime-data"
MANIFEST_VERSION = 1
SQLITE_HEADER = b"SQLite format 3\x00"
PLUGIN_KEYS = (
    "anti_recall",
    "auto_friend",
    "happy_bot",
    "invite",
    "keyword",
    "mc_status",
    "mc_update",
    "pig_bot",
    "wordcloud",
)
_PLUGIN_KEY_SET = frozenset(PLUGIN_KEYS)
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class MigrationError(RuntimeError):
    """The requested snapshot or restore operation is unsafe or invalid."""


@dataclass(frozen=True)
class _SourceFile:
    source: Path
    relative: PurePosixPath


@dataclass(frozen=True)
class _SourceDirectory:
    source: Path
    relative: PurePosixPath


@dataclass
class _Inventory:
    files: List[_SourceFile]
    directories: List[_SourceDirectory]


def _is_reparse(path: Path) -> bool:
    try:
        value = os.lstat(str(path))
    except OSError as exc:
        raise MigrationError("cannot inspect path: {}".format(path)) from exc
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(value.st_mode) or bool(attributes & reparse_flag)


def _lexists(path: Path) -> bool:
    return os.path.lexists(str(path))


def _absolute_path(value: PathLike, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise MigrationError("{} must be an absolute path".format(label))
    return Path(os.path.normpath(str(path)))


def _check_path_chain(path: Path, label: str) -> None:
    existing = path
    while not _lexists(existing):
        parent = existing.parent
        if parent == existing:
            raise MigrationError("{} has no existing ancestor".format(label))
        existing = parent
    chain = [existing]
    while chain[-1].parent != chain[-1]:
        chain.append(chain[-1].parent)
    for component in reversed(chain):
        if _is_reparse(component):
            raise MigrationError("{} passes through a symbolic link or reparse point".format(label))


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_endpoints(source: PathLike, destination: PathLike) -> Tuple[Path, Path]:
    source_path = _absolute_path(source, "source")
    destination_path = _absolute_path(destination, "destination")
    _check_path_chain(source_path, "source")
    _check_path_chain(destination_path.parent, "destination")
    if not source_path.is_dir() or _is_reparse(source_path):
        raise MigrationError("source must be an existing ordinary directory")
    if not destination_path.parent.is_dir():
        raise MigrationError("destination parent must already exist")
    source_real = _resolved(source_path)
    destination_real = _resolved(destination_path)
    if source_real == destination_real or _inside(source_real, destination_real) or _inside(destination_real, source_real):
        raise MigrationError("source and destination must be separate, non-nested directories")
    return source_path, destination_path


def _safe_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise MigrationError("manifest contains an unsafe relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or relative.as_posix() != value:
        raise MigrationError("manifest contains an unsafe relative path")
    if any(part in ("", ".", "..") for part in relative.parts):
        raise MigrationError("manifest contains an unsafe relative path")
    if value == MANIFEST_NAME:
        raise MigrationError("manifest cannot list itself as runtime data")
    return relative


def _filesystem_path(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


def _scan_tree(source: Path, target: PurePosixPath) -> _Inventory:
    if not _lexists(source):
        return _Inventory([], [])
    _check_path_chain(source, "runtime data root")
    if _is_reparse(source) or not source.is_dir():
        raise MigrationError("runtime data root is not an ordinary directory: {}".format(source))
    files: List[_SourceFile] = []
    directories: List[_SourceDirectory] = [_SourceDirectory(source, target)]

    def visit(directory: Path, relative: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(str(directory)), key=lambda item: item.name)
        except OSError as exc:
            raise MigrationError("cannot read runtime data directory: {}".format(directory)) from exc
        for entry in entries:
            entry_path = Path(entry.path)
            if _is_reparse(entry_path):
                raise MigrationError("symbolic links and reparse points are not allowed in runtime data")
            entry_relative = relative / entry.name
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise MigrationError("cannot inspect runtime data entry: {}".format(entry_path)) from exc
            if stat.S_ISDIR(entry_stat.st_mode):
                directories.append(_SourceDirectory(entry_path, entry_relative))
                visit(entry_path, entry_relative)
            elif stat.S_ISREG(entry_stat.st_mode):
                files.append(_SourceFile(entry_path, entry_relative))
            else:
                raise MigrationError("runtime data may contain only ordinary files and directories")

    visit(source, target)
    return _Inventory(files, directories)


def _merge_inventory(parts: Iterable[_Inventory]) -> _Inventory:
    files: Dict[str, _SourceFile] = {}
    directories: Dict[str, _SourceDirectory] = {}
    for part in parts:
        for directory in part.directories:
            key = directory.relative.as_posix()
            if key in files:
                raise MigrationError("multiple source entries map to the same destination")
            directories.setdefault(key, directory)
        for item in part.files:
            key = item.relative.as_posix()
            if key in files or key in directories:
                raise MigrationError("multiple source entries map to the same destination")
            files[key] = item
    return _Inventory(
        [files[key] for key in sorted(files)],
        [directories[key] for key in sorted(directories)],
    )


def _validate_plugin_data_roots(project_root: Path) -> None:
    plugins = project_root / "xducraft_bot" / "plugins"
    if not _lexists(plugins):
        return
    if _is_reparse(plugins) or not plugins.is_dir():
        raise MigrationError("legacy plugin root is not an ordinary directory")
    for entry in sorted(os.scandir(str(plugins)), key=lambda item: item.name):
        plugin_path = Path(entry.path)
        if _is_reparse(plugin_path):
            raise MigrationError("legacy plugin directories cannot be links or reparse points")
        if not entry.is_dir(follow_symlinks=False):
            continue
        data_path = plugin_path / "data"
        if not _lexists(data_path):
            continue
        if _is_reparse(data_path) or not data_path.is_dir():
            raise MigrationError("legacy plugin data root is not an ordinary directory")
        if not entry.name.startswith("xducraft_"):
            raise MigrationError("unknown legacy plugin data directory: {}".format(entry.name))
        key = entry.name[len("xducraft_"):]
        if key not in _PLUGIN_KEY_SET:
            raise MigrationError("unknown legacy plugin data directory: {}".format(entry.name))


def _legacy_inventory(project_root: Path, config_db: Optional[PathLike]) -> _Inventory:
    _validate_plugin_data_roots(project_root)
    parts: List[_Inventory] = []
    shared_data = project_root / "xducraft_bot" / "shared" / "data"
    parts.append(_scan_tree(shared_data, PurePosixPath("core")))
    for key in PLUGIN_KEYS:
        legacy = project_root / "xducraft_bot" / "plugins" / ("xducraft_" + key) / "data"
        parts.append(_scan_tree(legacy, PurePosixPath("plugins") / key))
    image_cache = project_root / "xducraft_bot" / "plugins" / "xducraft_mc_status" / "image_cache"
    parts.append(_scan_tree(image_cache, PurePosixPath("cache") / "mc_status"))
    inventory = _merge_inventory(parts)

    env_config = os.environ.get("XDUCRAFT_CONFIG_DB")
    if env_config is not None and config_db is None:
        raise MigrationError(
            "XDUCRAFT_CONFIG_DB is set; pass --config-db explicitly instead of relying on process environment"
        )
    if config_db is not None:
        config_path = _absolute_path(config_db, "config-db")
        _check_path_chain(config_path, "config-db")
        if not config_path.is_file() or _is_reparse(config_path):
            raise MigrationError("config-db must be an existing ordinary file")
        if not _is_sqlite(config_path):
            raise MigrationError("config-db is not a SQLite database")
        target = "core/configuration.sqlite3"
        replaced_paths = {target + suffix for suffix in ("",) + _SIDECAR_SUFFIXES}
        inventory.files = [
            item for item in inventory.files
            if item.relative.as_posix() not in replaced_paths
        ]
        inventory.files.append(_SourceFile(config_path, PurePosixPath(target)))
        inventory.files.sort(key=lambda item: item.relative.as_posix())
    if not inventory.files and not inventory.directories:
        raise MigrationError("no recognized legacy runtime data was found")
    return inventory


def _runtime_inventory(runtime_root: Path) -> _Inventory:
    allowed_top = {"core", "plugins", "cache", MANIFEST_NAME}
    try:
        entries = sorted(os.scandir(str(runtime_root)), key=lambda item: item.name)
    except OSError as exc:
        raise MigrationError("cannot read runtime source") from exc
    for entry in entries:
        path = Path(entry.path)
        if _is_reparse(path):
            raise MigrationError("runtime source contains a link or reparse point")
        if entry.name not in allowed_top:
            raise MigrationError("unknown entry at runtime root: {}".format(entry.name))
        if entry.name == MANIFEST_NAME and not entry.is_file(follow_symlinks=False):
            raise MigrationError("runtime manifest path is not an ordinary file")

    plugins = runtime_root / "plugins"
    if plugins.exists():
        if _is_reparse(plugins) or not plugins.is_dir():
            raise MigrationError("runtime plugins root is not an ordinary directory")
        for entry in os.scandir(str(plugins)):
            path = Path(entry.path)
            if _is_reparse(path) or not entry.is_dir(follow_symlinks=False):
                raise MigrationError("runtime plugin roots must be ordinary directories")
            if entry.name not in _PLUGIN_KEY_SET:
                raise MigrationError("unknown runtime plugin key: {}".format(entry.name))

    cache = runtime_root / "cache"
    if cache.exists():
        if _is_reparse(cache) or not cache.is_dir():
            raise MigrationError("runtime cache root is not an ordinary directory")
        for entry in os.scandir(str(cache)):
            path = Path(entry.path)
            if _is_reparse(path) or not entry.is_dir(follow_symlinks=False):
                raise MigrationError("runtime cache roots must be ordinary directories")
            if entry.name != "mc_status":
                raise MigrationError("unknown runtime cache key: {}".format(entry.name))

    parts = [
        _scan_tree(runtime_root / "core", PurePosixPath("core")),
        _scan_tree(plugins, PurePosixPath("plugins")),
        _scan_tree(cache, PurePosixPath("cache")),
    ]
    inventory = _merge_inventory(parts)
    if not inventory.files and not inventory.directories:
        raise MigrationError("no runtime data was found")
    return inventory


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            header = stream.read(len(SQLITE_HEADER))
    except OSError as exc:
        raise MigrationError("cannot read source file: {}".format(path)) from exc
    return header == SQLITE_HEADER or path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}


def _sqlite_source_uri(path: Path) -> str:
    return path.resolve(strict=True).as_uri() + "?mode=ro"


def _sqlite_source_state(source: Path) -> Dict[str, Optional[Tuple[int, int]]]:
    state: Dict[str, Optional[Tuple[int, int]]] = {}
    for suffix in ("",) + _SIDECAR_SUFFIXES:
        path = Path(str(source) + suffix)
        if not _lexists(path):
            state[suffix] = None
            continue
        if _is_reparse(path):
            raise MigrationError("SQLite source files cannot be links or reparse points")
        value = os.lstat(str(path))
        if not stat.S_ISREG(value.st_mode):
            raise MigrationError("SQLite source files must be ordinary files")
        state[suffix] = (value.st_size, value.st_mtime_ns)
    return state


def _backup_sqlite(source: Path, destination: Path) -> None:
    initial_state = _sqlite_source_state(source)
    source_connection: Optional[sqlite3.Connection] = None
    destination_connection: Optional[sqlite3.Connection] = None
    try:
        with tempfile.TemporaryDirectory(prefix="xducraft-sqlite-input-") as temporary:
            private_source = Path(temporary) / source.name
            shutil.copyfile(str(source), str(private_source))
            for suffix in ("-wal", "-journal"):
                if initial_state[suffix] is not None:
                    shutil.copyfile(str(source) + suffix, str(private_source) + suffix)
            if _sqlite_source_state(source) != initial_state:
                raise MigrationError("SQLite source changed while its private input was copied")

            try:
                source_connection = sqlite3.connect(_sqlite_source_uri(private_source), uri=True)
                source_connection.execute("PRAGMA query_only = ON")
                destination_connection = sqlite3.connect(str(destination))
                source_connection.backup(destination_connection)
                result = destination_connection.execute("PRAGMA integrity_check").fetchall()
                if result != [("ok",)]:
                    raise MigrationError("SQLite backup failed integrity_check: {}".format(source.name))
            finally:
                if destination_connection is not None:
                    destination_connection.close()
                    destination_connection = None
                if source_connection is not None:
                    source_connection.close()
                    source_connection = None
    except sqlite3.Error as exc:
        raise MigrationError("cannot create verified SQLite backup: {}".format(source.name)) from exc
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
        if _sqlite_source_state(source) != initial_state:
            raise MigrationError("SQLite source changed while its private backup was created")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(destination) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    shutil.copystat(str(source), str(destination), follow_symlinks=False)
    if _sqlite_source_state(source) != initial_state:
        raise MigrationError("SQLite source changed while its backup metadata was copied")


def _sqlite_main_files(files: Sequence[_SourceFile]) -> Set[Path]:
    return {item.source for item in files if _is_sqlite(item.source)}


def _sidecar_main(path: Path) -> Optional[Path]:
    name = path.name
    for suffix in _SIDECAR_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return path.with_name(name[:-len(suffix)])
    return None


def _copy_inventory(inventory: _Inventory, destination: Path) -> None:
    sqlite_files = _sqlite_main_files(inventory.files)
    omitted: Set[Path] = set()
    for item in inventory.files:
        possible_main = _sidecar_main(item.source)
        if possible_main is not None:
            if possible_main in sqlite_files:
                omitted.add(item.source)
            else:
                raise MigrationError("orphan SQLite sidecar cannot be treated as authoritative data")

    for directory in sorted(inventory.directories, key=lambda item: len(item.relative.parts)):
        _filesystem_path(destination, directory.relative).mkdir(parents=True, exist_ok=True)
    for item in inventory.files:
        if item.source in omitted:
            continue
        target = _filesystem_path(destination, item.relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if item.source in sqlite_files:
            _backup_sqlite(item.source, target)
        else:
            before = item.source.stat()
            shutil.copy2(str(item.source), str(target), follow_symlinks=False)
            after = item.source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise MigrationError("source file changed while it was being copied")
    for directory in sorted(inventory.directories, key=lambda item: len(item.relative.parts), reverse=True):
        target = _filesystem_path(destination, directory.relative)
        shutil.copystat(str(directory.source), str(target), follow_symlinks=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _tree_entries(root: Path) -> Tuple[List[str], List[Mapping[str, object]]]:
    directories: List[str] = []
    files: List[Mapping[str, object]] = []

    def visit(directory: Path, relative: PurePosixPath) -> None:
        for entry in sorted(os.scandir(str(directory)), key=lambda item: item.name):
            path = Path(entry.path)
            if _is_reparse(path):
                raise MigrationError("snapshot contains a link or reparse point")
            item_relative = relative / entry.name if relative.parts else PurePosixPath(entry.name)
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                directories.append(item_relative.as_posix())
                visit(path, item_relative)
            elif stat.S_ISREG(info.st_mode):
                if item_relative.as_posix() == MANIFEST_NAME:
                    continue
                files.append({
                    "path": item_relative.as_posix(),
                    "sha256": _sha256(path),
                    "size": info.st_size,
                })
            else:
                raise MigrationError("snapshot contains a non-ordinary filesystem entry")

    visit(root, PurePosixPath())
    return directories, files


def _manifest_payload(root: Path, source_layout: str) -> Mapping[str, object]:
    directories, files = _tree_entries(root)
    return {
        "format": MANIFEST_FORMAT,
        "version": MANIFEST_VERSION,
        "layout": "runtime",
        "source_layout": source_layout,
        "directories": directories,
        "files": files,
    }


def _write_manifest(root: Path, source_layout: str) -> Mapping[str, object]:
    payload = _manifest_payload(root, source_layout)
    manifest = root / MANIFEST_NAME
    with manifest.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        os.chmod(str(manifest), 0o600)
    return payload


def _read_manifest(root: Path) -> Mapping[str, object]:
    manifest = root / MANIFEST_NAME
    if not manifest.is_file() or _is_reparse(manifest):
        raise MigrationError("snapshot has no ordinary manifest file")
    try:
        if manifest.stat().st_size > 8 * 1024 * 1024:
            raise MigrationError("snapshot manifest is unreasonably large")
        with manifest.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError("snapshot manifest is unreadable") from exc
    if not isinstance(payload, dict):
        raise MigrationError("snapshot manifest must be a JSON object")
    return payload


def _validated_manifest(root: Path) -> Mapping[str, object]:
    payload = _read_manifest(root)
    expected_keys = {
        "format", "version", "layout", "source_layout", "directories", "files",
    }
    if set(payload) != expected_keys:
        raise MigrationError("snapshot manifest fields are invalid")
    if payload.get("format") != MANIFEST_FORMAT or type(payload.get("version")) is not int:
        raise MigrationError("snapshot manifest format or version is unsupported")
    if payload.get("version") != MANIFEST_VERSION:
        raise MigrationError("snapshot manifest format or version is unsupported")
    if payload.get("layout") != "runtime" or payload.get("source_layout") not in ("legacy", "runtime"):
        raise MigrationError("snapshot manifest layout is invalid")
    raw_directories = payload.get("directories")
    raw_files = payload.get("files")
    if not isinstance(raw_directories, list) or not isinstance(raw_files, list):
        raise MigrationError("snapshot manifest inventory is invalid")

    expected_directories: Set[str] = set()
    for value in raw_directories:
        relative = _safe_relative(value)
        normalized = relative.as_posix()
        if normalized in expected_directories:
            raise MigrationError("snapshot manifest contains duplicate directories")
        expected_directories.add(normalized)

    expected_files: Dict[str, Tuple[int, str]] = {}
    for entry in raw_files:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise MigrationError("snapshot manifest file entry is invalid")
        relative = _safe_relative(entry.get("path"))
        size = entry.get("size")
        checksum = entry.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise MigrationError("snapshot manifest file size is invalid")
        if not isinstance(checksum, str) or not _HASH_RE.fullmatch(checksum):
            raise MigrationError("snapshot manifest checksum is invalid")
        normalized = relative.as_posix()
        if normalized in expected_files or normalized in expected_directories:
            raise MigrationError("snapshot manifest contains duplicate paths")
        expected_files[normalized] = (size, checksum)

    actual_directories, actual_files_raw = _tree_entries(root)
    actual_files = {entry["path"]: (entry["size"], entry["sha256"]) for entry in actual_files_raw}
    if set(actual_directories) != expected_directories or actual_files != expected_files:
        raise MigrationError("snapshot contents do not match its manifest")
    return payload




def _new_temporary_destination(destination: Path) -> Path:
    return Path(tempfile.mkdtemp(prefix=".{}.tmp-".format(destination.name), dir=str(destination.parent)))

def _remove_temporary(path: Path) -> None:
    def make_writable(function, name, ignored_error):
        del ignored_error
        os.chmod(name, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        function(name)

    shutil.rmtree(str(path), onerror=make_writable)


def _publish(temporary: Path, destination: Path) -> None:
    if _lexists(destination):
        raise MigrationError("destination appeared while the operation was running")
    os.rename(str(temporary), str(destination))


def migrate(
    source: PathLike,
    destination: PathLike,
    source_layout: str = "legacy",
    config_db: Optional[PathLike] = None,
) -> str:
    """Create a verified runtime-layout snapshot; return its completion status."""
    source_path, destination_path = _validate_endpoints(source, destination)
    if source_layout not in ("legacy", "runtime"):
        raise MigrationError("source_layout must be 'legacy' or 'runtime'")
    if source_layout == "runtime" and config_db is not None:
        raise MigrationError("config_db applies only to a legacy source layout")

    existing_manifest: Optional[Mapping[str, object]] = None
    if _lexists(destination_path):
        if _is_reparse(destination_path) or not destination_path.is_dir():
            raise MigrationError("destination already exists and is not a verified snapshot")
        existing_manifest = _validated_manifest(destination_path)

    inventory = (
        _legacy_inventory(source_path, config_db)
        if source_layout == "legacy"
        else _runtime_inventory(source_path)
    )
    destination_real = _resolved(destination_path)
    for item in inventory.files:
        if _inside(_resolved(item.source), destination_real):
            raise MigrationError("a source data file cannot be inside the destination")
    temporary = _new_temporary_destination(destination_path)
    published = False
    try:
        _copy_inventory(inventory, temporary)
        candidate_manifest = _write_manifest(temporary, source_layout)
        _validated_manifest(temporary)
        if existing_manifest is not None:
            if existing_manifest == candidate_manifest:
                return "already-complete"
            raise MigrationError("destination is complete but does not match the current source")
        _publish(temporary, destination_path)
        published = True
        return "migrated"
    finally:
        if not published and temporary.exists():
            _remove_temporary(temporary)


def _runtime_restore_inventory(source: Path) -> _Inventory:
    parts: List[_Inventory] = []
    core = source / "core"
    parts.append(_scan_tree(core, PurePosixPath("xducraft_bot/shared/data")))

    plugins = source / "plugins"
    if plugins.exists():
        if _is_reparse(plugins) or not plugins.is_dir():
            raise MigrationError("snapshot plugins root is invalid")
        for entry in sorted(os.scandir(str(plugins)), key=lambda item: item.name):
            path = Path(entry.path)
            if _is_reparse(path) or not entry.is_dir(follow_symlinks=False):
                raise MigrationError("snapshot plugin root is invalid")
            if entry.name not in _PLUGIN_KEY_SET:
                raise MigrationError("snapshot contains an unknown plugin key")
            target = PurePosixPath("xducraft_bot/plugins") / ("xducraft_" + entry.name) / "data"
            parts.append(_scan_tree(path, target))

    cache = source / "cache"
    if cache.exists():
        if _is_reparse(cache) or not cache.is_dir():
            raise MigrationError("snapshot cache root is invalid")
        for entry in sorted(os.scandir(str(cache)), key=lambda item: item.name):
            path = Path(entry.path)
            if _is_reparse(path) or not entry.is_dir(follow_symlinks=False) or entry.name != "mc_status":
                raise MigrationError("snapshot contains an unknown cache key")
            target = PurePosixPath("xducraft_bot/plugins/xducraft_mc_status/image_cache")
            parts.append(_scan_tree(path, target))
    return _merge_inventory(parts)


def restore(source: PathLike, destination: PathLike) -> str:
    """Restore a verified runtime snapshot into a new legacy-layout root."""
    source_path, destination_path = _validate_endpoints(source, destination)
    if _lexists(destination_path):
        raise MigrationError("restore destination must not already exist")
    _validated_manifest(source_path)
    _runtime_inventory(source_path)
    inventory = _runtime_restore_inventory(source_path)
    temporary = _new_temporary_destination(destination_path)
    published = False
    try:
        _copy_inventory(inventory, temporary)
        _publish(temporary, destination_path)
        published = True
        return "restored"
    finally:
        if not published and temporary.exists():
            _remove_temporary(temporary)


def _parser() -> argparse.ArgumentParser:
    warning = (
        "OFFLINE SOURCE REQUIRED: stop NoneBot and every other writer first. "
        "This tool does not stop processes or prove writers are inactive. SQLite backups are "
        "transaction-consistent, but consistency across databases, JSON, and media requires an "
        "offline source. Snapshots may contain raw credentials and are not encrypted; Windows ACL "
        "hardening is outside this tool."
    )
    parser = argparse.ArgumentParser(
        description="Migrate or restore XDUCraft runtime data without importing the bot.",
        epilog=warning,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate_parser = subparsers.add_parser("migrate", help="create a new runtime-layout snapshot", epilog=warning)
    migrate_parser.add_argument("--source", required=True, help="absolute legacy project root or runtime root")
    migrate_parser.add_argument("--destination", required=True, help="absolute new snapshot directory")
    migrate_parser.add_argument(
        "--source-layout", choices=("legacy", "runtime"), default="legacy",
        help="interpret source as legacy checkout data or a runtime layout (default: legacy)",
    )
    migrate_parser.add_argument(
        "--config-db",
        help="absolute active external configuration SQLite database for a legacy source",
    )
    restore_parser = subparsers.add_parser("restore", help="restore a verified snapshot to a new legacy-layout root", epilog=warning)
    restore_parser.add_argument("--source", required=True, help="absolute verified runtime-layout snapshot")
    restore_parser.add_argument("--destination", required=True, help="absolute new legacy-layout root")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "migrate":
            status = migrate(
                arguments.source,
                arguments.destination,
                source_layout=arguments.source_layout,
                config_db=arguments.config_db,
            )
        else:
            status = restore(arguments.source, arguments.destination)
    except (MigrationError, OSError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2
    print("{}: {}".format(status, arguments.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
