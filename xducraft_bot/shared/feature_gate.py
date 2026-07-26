"""群级功能开关（功能隔离）。

要求很明确：**未启用的群里不应该触发任何反应**。

难点在于各插件的“启用状态”存放位置本来就不一样（词云在自己的 config、
猪猪图在自己的 json、MC 更新推送是一个订阅群号列表）。强行把它们迁移到
一份新文件既有丢配置的风险，也没必要。

所以这里做的是一个**注册表 + 可插拔后端**：

- 没有自带存储的功能（新插件、happy_bot、mc_status）直接用共享 JSON 存储；
- 已有存储的功能（词云 / 猪猪图 / MC 更新）注册自己的 getter/setter，
  开关状态仍然落在原文件里，但对外暴露统一的查询接口。

这样 ``/功能`` 指令能一次列出所有插件在本群的状态，而各插件内部实现不用动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from nonebot.log import logger

from .json_store import JsonStore, as_bool

SHARED_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FEATURE_STATE_FILE = os.path.join(SHARED_DATA_DIR, "feature_gate.json")

# is_enabled 的判定来源，用于在 /功能 里告诉管理员“为什么是这个值”。
SOURCE_GROUP = "group"
SOURCE_DEFAULT = "default"


def _default_state() -> Dict[str, Any]:
    return {"groups": {}, "defaults": {}}


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

    raw_defaults = raw.get("defaults", {})
    if isinstance(raw_defaults, dict):
        state["defaults"] = {
            str(key): as_bool(value)
            for key, value in raw_defaults.items()
            if isinstance(key, str) and key
        }

    return state


_store: JsonStore = JsonStore(FEATURE_STATE_FILE, _default_state, _normalize_state)


@dataclass
class Feature:
    """一个可被群管理员开关的功能。

    Attributes:
        key: 稳定的英文标识，作为存储键，不要随意改名。
        name: 展示用中文名。
        description: 一句话说明这个开关控制什么。
        default_enabled: 群里没有显式配置时的取值。
        passive: 是否会在**没有人主动发指令**的情况下发言/反应。
            被动功能（自动推送、关键词回复、贴表情）默认必须是关的，
            否则机器人一进群就开始刷屏。
        getter: 可选。已有独立存储的插件在这里提供 ``(group_id) -> bool``。
        setter: 可选。对应的 ``(group_id, enabled) -> changed``。
        lister: 可选。对应的 ``() -> Iterable[int]``，列出已启用的群。
        superuser_only: 是否只有 SUPERUSER 才能修改。用于全局推送等原本就不
            允许群管理员配置的功能；统一面板不能意外扩大权限。
    """

    key: str
    name: str
    description: str = ""
    default_enabled: bool = False
    passive: bool = False
    getter: Optional[Callable[[int], bool]] = field(default=None, repr=False)
    setter: Optional[Callable[[int, bool], bool]] = field(default=None, repr=False)
    lister: Optional[Callable[[], Iterable[int]]] = field(default=None, repr=False)
    superuser_only: bool = False

    @property
    def uses_shared_store(self) -> bool:
        return self.getter is None


_registry: Dict[str, Feature] = {}


def register(feature: Feature) -> Feature:
    """注册一个功能开关。重复注册同一 key 会覆盖并记一条 warning。"""
    if feature.key in _registry:
        logger.warning("[FeatureGate] 功能 {} 被重复注册，后者覆盖前者。", feature.key)
    if feature.passive and feature.default_enabled:
        # 这是设计约束而不是口头约定：被动功能默认开就等于默认刷屏。
        logger.warning(
            "[FeatureGate] 被动功能 {} 默认开启，已强制改为默认关闭。", feature.key
        )
        feature.default_enabled = False
    _registry[feature.key] = feature
    return feature


def get_feature(key: str) -> Optional[Feature]:
    return _registry.get(key)


def all_features() -> List[Feature]:
    """按注册顺序返回全部功能。"""
    return list(_registry.values())


def resolve(key: str, group_id: int) -> Tuple[bool, str]:
    """返回 ``(是否启用, 判定来源)``。

    来源为 ``group`` 表示本群有显式配置，``default`` 表示走的是默认值。
    """
    feature = _registry.get(key)

    if feature is not None and feature.getter is not None:
        # 自带存储的插件：状态由它自己说了算，无法区分来源，统一记为 group。
        try:
            return bool(feature.getter(int(group_id))), SOURCE_GROUP
        except Exception as exc:
            logger.error("[FeatureGate] 读取功能 {} 状态失败: {}", key, exc)
            return (feature.default_enabled, SOURCE_DEFAULT)

    state = _store.load()
    group_key = str(int(group_id))
    group_features = state["groups"].get(group_key, {})
    if key in group_features:
        return bool(group_features[key]), SOURCE_GROUP

    if key in state["defaults"]:
        return bool(state["defaults"][key]), SOURCE_DEFAULT

    if feature is not None:
        return feature.default_enabled, SOURCE_DEFAULT
    return False, SOURCE_DEFAULT


def is_enabled(key: str, group_id: Optional[int]) -> bool:
    """本群是否启用了该功能。``group_id`` 为 None（私聊）时一律视为未启用。"""
    if group_id is None:
        return False
    enabled, _ = resolve(key, group_id)
    return enabled


def set_enabled(key: str, group_id: int, enabled: bool) -> bool:
    """设置开关，返回是否**发生了变化**。"""
    feature = _registry.get(key)

    if feature is not None and feature.setter is not None:
        try:
            return bool(feature.setter(int(group_id), bool(enabled)))
        except Exception as exc:
            logger.error("[FeatureGate] 写入功能 {} 状态失败: {}", key, exc)
            return False

    group_key = str(int(group_id))
    target = bool(enabled)

    def _mutate(state: Dict[str, Any]) -> bool:
        group_features = state["groups"].setdefault(group_key, {})
        if group_features.get(key) == target:
            return False
        group_features[key] = target
        return True

    return bool(_store.mutate(_mutate))


def clear_override(key: str, group_id: int) -> bool:
    """删除本群的显式配置，回退到默认值。返回是否真的删掉了东西。"""
    feature = _registry.get(key)
    if feature is not None and feature.setter is not None:
        # 自带存储的插件没有“未配置”这个状态，无法清除。
        return False

    group_key = str(int(group_id))

    def _mutate(state: Dict[str, Any]) -> bool:
        group_features = state["groups"].get(group_key)
        if not group_features or key not in group_features:
            return False
        del group_features[key]
        if not group_features:
            state["groups"].pop(group_key, None)
        return True

    return bool(_store.mutate(_mutate))


def set_default(key: str, enabled: bool) -> bool:
    """设置某功能的全局默认值（对所有没有显式配置的群生效）。"""
    target = bool(enabled)

    def _mutate(state: Dict[str, Any]) -> bool:
        if state["defaults"].get(key) == target:
            return False
        state["defaults"][key] = target
        return True

    return bool(_store.mutate(_mutate))


def list_enabled_groups(key: str) -> List[int]:
    """列出显式启用了该功能的群。

    只统计**显式开启**的群：默认值是给“未知的群”兜底的，不能被枚举出来当作
    推送目标，否则一个默认开启的功能会向机器人所在的所有群推送。
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
    """仅供测试：清空注册表与缓存。"""
    _registry.clear()
    _store.invalidate()


__all__ = [
    "Feature",
    "register",
    "get_feature",
    "all_features",
    "resolve",
    "is_enabled",
    "set_enabled",
    "clear_override",
    "set_default",
    "list_enabled_groups",
    "describe_group",
    "SOURCE_GROUP",
    "SOURCE_DEFAULT",
]
