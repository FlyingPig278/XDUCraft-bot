"""Registered feature preferences and total plugin gates.

Shared feature preferences use the unified SQLite configuration database.
Plugin-owned feature backends remain authoritative for business state such as
subscriptions. Total plugin stop gates execution without discarding preferences.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from nonebot.log import logger

from .config_store import ConfigDocumentStore, database
from .configuration import is_plugin_enabled, owner_of_feature, set_plugin_enabled
from .data_paths import shared_data_dir
from .json_store import as_bool

SHARED_DATA_DIR = str(shared_data_dir())
FEATURE_STATE_FILE = os.path.join(SHARED_DATA_DIR, "feature_gate.json")

# is_enabled 的判定来源，用于在 /功能 里告诉管理员“为什么是这个值”。
SOURCE_GROUP = "group"
SOURCE_DEFAULT = "default"


def _default_state() -> Dict[str, Any]:
    return {"groups": {}}


def _normalize_state(raw: Any) -> Dict[str, Any]:
    state = _default_state()
    if not isinstance(raw, dict):
        return state

    raw_groups = raw.get("groups", {})
    if isinstance(raw_groups, dict):
        for group_id, features in raw_groups.items():
            if not isinstance(features, dict):
                continue
            try:
                group_key = str(int(group_id))
            except (TypeError, ValueError):
                continue
            normalized = {
                str(key): as_bool(value)
                for key, value in features.items()
                if isinstance(key, str) and key
            }
            if normalized:
                state["groups"][group_key] = normalized



    return state


_store = ConfigDocumentStore("feature_gate", _default_state, _normalize_state, legacy_path=FEATURE_STATE_FILE)


def migrate_legacy_state() -> Dict[str, Any]:
    """Import the former feature-gate JSON once, then use SQLite only."""
    return _store.load()


@dataclass
class Feature:
    """一个可被群管理员开关的功能。

    Attributes:
        key: 稳定的英文标识，作为存储键，不要随意改名。
        name: 展示用中文名。
        description: 一句话说明这个开关控制什么。
        passive: 是否会在**没有人主动发指令**的情况下发言/反应。
            所有未配置的群功能均为关闭；该字段只描述运行方式。
        getter: 可选。已有独立存储的插件在这里提供 ``(group_id) -> bool``。
        setter: 可选。对应的 ``(group_id, enabled) -> changed``。
        lister: 可选。对应的 ``() -> Iterable[int]``，列出已启用的群。
        superuser_only: 是否只有 SUPERUSER 才能修改。用于全局推送等原本就不
            允许群管理员配置的功能；统一面板不能意外扩大权限。
    """

    key: str
    name: str
    description: str = ""
    passive: bool = False
    getter: Optional[Callable[[int], bool]] = field(default=None, repr=False)
    setter: Optional[Callable[[int, bool], bool]] = field(default=None, repr=False)
    lister: Optional[Callable[[], Iterable[int]]] = field(default=None, repr=False)
    superuser_only: bool = False

    @property
    def uses_shared_store(self) -> bool:
        return self.getter is None


_registry: Dict[str, Feature] = {}
_write_lock = RLock()


def register(feature: Feature) -> Feature:
    """注册一个功能开关。重复注册同一 key 会覆盖并记一条 warning。"""
    if feature.key in _registry:
        logger.warning("[FeatureGate] 功能 {} 被重复注册，后者覆盖前者。", feature.key)

    _registry[feature.key] = feature
    owner = owner_of_feature(feature.key)
    if owner is not None and owner.managed and owner.feature_keys == (feature.key,):
        try:
            if feature.lister is not None:
                candidates = {int(group_id) for group_id in feature.lister()}
                enabled_groups = {
                    group_id for group_id in candidates
                    if feature.getter is None or bool(feature.getter(group_id))
                }
            elif feature.getter is None:
                state = _store.load()
                enabled_groups = {
                    int(group_id)
                    for group_id, features in state["groups"].items()
                    if features.get(feature.key) is True
                }
            else:
                enabled_groups = None
            if enabled_groups is not None:
                from .config_store import database
                database().materialize_feature_controls(
                    owner.key, feature.key, enabled_groups,
                )
        except Exception as exc:
            logger.error("[FeatureGate] 迁移功能 {} 的插件开关失败: {}", feature.key, exc)
    return feature


def get_feature(key: str) -> Optional[Feature]:
    return _registry.get(key)


def all_features() -> List[Feature]:
    """按注册顺序返回全部功能。"""
    return list(_registry.values())


def resolve(key: str, group_id: int) -> Tuple[bool, str]:
    """Return the saved group preference; absence is always off."""
    feature = _registry.get(key)

    if feature is not None and feature.getter is not None:
        try:
            return bool(feature.getter(int(group_id))), SOURCE_GROUP
        except Exception as exc:
            logger.error("[FeatureGate] 读取功能 {} 状态失败: {}", key, exc)
            return False, SOURCE_DEFAULT

    state = _store.load()
    group_key = str(int(group_id))
    group_features = state["groups"].get(group_key, {})
    if key in group_features:
        return bool(group_features[key]), SOURCE_GROUP
    return False, SOURCE_DEFAULT


def is_enabled(key: str, group_id: Optional[int]) -> bool:
    """本群是否启用了该功能。``group_id`` 为 None（私聊）时一律视为未启用。"""
    if group_id is None:
        return False
    owner = owner_of_feature(key)
    if owner is not None and not is_plugin_enabled(owner.key, group_id):
        return False
    enabled, _ = resolve(key, group_id)
    return enabled


def _set_enabled(key: str, group_id: int, enabled: bool) -> bool:
    """Save one group preference and synchronize a sole-feature plugin gate.

    Plugin-owned setters run first so their validation and eligibility checks
    remain authoritative.  The group total switch is mirrored only after the
    underlying store can be read back at the requested value.
    """
    feature = _registry.get(key)
    group_id = int(group_id)
    target = bool(enabled)
    preference_changed = False

    if feature is not None and feature.setter is not None:
        if feature.getter is None:
            logger.error("[FeatureGate] 功能 {} 提供 setter 但没有 getter，拒绝同步", key)
            return False
        try:
            before = bool(feature.getter(group_id))
            setter_changed = bool(feature.setter(group_id, target))
            current = bool(feature.getter(group_id))
        except Exception as exc:
            logger.error("[FeatureGate] 写入功能 {} 状态失败: {}", key, exc)
            return False
        if current != target:
            logger.warning("[FeatureGate] 功能 {} 写入后未达到目标状态", key)
            return False
        preference_changed = setter_changed or before != current
    else:
        group_key = str(group_id)

        def _mutate(state: Dict[str, Any]) -> bool:
            group_features = state["groups"].setdefault(group_key, {})
            if key in group_features and group_features[key] == target:
                return False
            group_features[key] = target
            return True

        try:
            preference_changed = bool(_store.mutate(_mutate))
            current, _ = resolve(key, group_id)
        except Exception as exc:
            logger.error("[FeatureGate] 写入功能 {} 状态失败: {}", key, exc)
            return False
        if current != target:
            logger.warning("[FeatureGate] 功能 {} 写入后未达到目标状态", key)
            return False

    owner = owner_of_feature(key)
    control_changed = False
    if owner is not None and owner.feature_keys == (key,):
        try:
            from .config_store import database
            before_control = database().control(owner.key, group_id)["raw"][1]
            set_plugin_enabled(owner.key, target, group_id, actor="feature_gate")
            after_control = database().control(owner.key, group_id)["raw"][1]
            control_changed = before_control != after_control
        except Exception as exc:
            logger.error("[FeatureGate] 同步功能 {} 的插件开关失败: {}", key, exc)
            return False
    return preference_changed or control_changed


def set_enabled(key: str, group_id: int, enabled: bool) -> bool:
    with _write_lock:
        return _set_enabled(key, group_id, enabled)



def list_configured_groups() -> List[int]:
    """列出配置核心与功能记录中已知的正整数群号。"""
    groups = set(database().list_known_groups())
    for group_key in _store.load()["groups"]:
        try:
            group_id = int(group_key)
        except (TypeError, ValueError):
            continue
        if group_id > 0:
            groups.add(group_id)
    return sorted(groups)



def list_enabled_groups(key: str) -> List[int]:
    """列出显式启用了该功能的群。

    未保存偏好的群始终关闭，因此只能枚举显式开启或插件自有存储中的群。
    """
    feature = _registry.get(key)
    if feature is not None and feature.lister is not None:
        try:
            return sorted({int(gid) for gid in feature.lister()})
        except Exception as exc:
            logger.error("[FeatureGate] 枚举功能 {} 的群失败: {}", key, exc)
            return []

    state = _store.load()
    groups: List[int] = []
    for group_key, features in state["groups"].items():
        if features.get(key) is True:
            try:
                groups.append(int(group_key))
            except (TypeError, ValueError):
                continue
    return sorted(groups)


def describe_group(group_id: int) -> List[Dict[str, Any]]:
    """给 ``/功能`` 指令用：本群所有功能的状态快照。"""
    snapshot = []
    for feature in all_features():
        enabled, source = resolve(feature.key, group_id)
        snapshot.append(
            {
                "key": feature.key,
                "name": feature.name,
                "description": feature.description,
                "passive": feature.passive,
                "enabled": enabled,
                "source": source,
                "configurable": feature.setter is not None or feature.uses_shared_store,
                "superuser_only": feature.superuser_only,
            }
        )
    return snapshot


def reset_for_tests() -> None:
    """仅供测试：清空功能注册表；SQLite 不维护配置读缓存。"""
    _registry.clear()


__all__ = [
    "Feature",
    "register",
    "get_feature",
    "all_features",
    "resolve",
    "is_enabled",
    "is_plugin_enabled",
    "set_enabled",
    "list_configured_groups",
    "list_enabled_groups",
    "describe_group",
    "SOURCE_GROUP",
    "SOURCE_DEFAULT",
]
