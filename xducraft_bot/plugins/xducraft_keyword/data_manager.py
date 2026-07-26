"""关键词回复的配置存储。

规则同时支持**群级**和**全局**两层：全局规则（如“新手教程”）在所有启用的群里
都生效，群级规则只在本群生效；同一关键词命中时群级优先。

回复内容以 CQ 码字符串保存。里面的图片会在**添加时**就下载到本地——预设回复
是长期使用的，直接存 QQ 的临时 URL 过几天就会变成裂图。
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from xducraft_bot.shared.json_store import JsonStore, as_bool, as_int, as_str

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "keyword_config.json")
MEDIA_DIR = os.path.join(DATA_DIR, "media")

#: 匹配方式。
MATCH_CONTAINS = "contains"   # 消息里包含关键词
MATCH_EXACT = "exact"         # 整条消息与关键词完全相同
MATCH_PREFIX = "prefix"       # 消息以关键词开头
MATCH_REGEX = "regex"         # 正则匹配
MATCH_MODES = (MATCH_CONTAINS, MATCH_EXACT, MATCH_PREFIX, MATCH_REGEX)

MATCH_LABELS = {
    MATCH_CONTAINS: "包含",
    MATCH_EXACT: "完全匹配",
    MATCH_PREFIX: "开头匹配",
    MATCH_REGEX: "正则",
}

#: 参与匹配的消息长度上限，挡住超长文本 + 正则造成的卡顿。
MAX_MATCH_LENGTH = 500
MAX_KEYWORD_LENGTH = 64
MAX_REPLY_LENGTH = 4096
MAX_RULES_PER_SCOPE = 200


def _default_config() -> Dict[str, Any]:
    return {
        "global_rules": [],
        "groups": {},
        # 同一条规则在同一个群里的最小触发间隔（秒），防刷屏。
        "default_cooldown": 10,
    }


def _normalize_rule(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    keywords = raw.get("keywords")
    if isinstance(keywords, str):
        keywords = [keywords]
    if not isinstance(keywords, list):
        return None

    cleaned = []
    for keyword in keywords:
        text = as_str(keyword)[:MAX_KEYWORD_LENGTH]
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        return None

    reply = as_str(raw.get("reply"))[:MAX_REPLY_LENGTH]
    if not reply:
        return None

    match = as_str(raw.get("match"), MATCH_CONTAINS).lower()
    if match not in MATCH_MODES:
        match = MATCH_CONTAINS

    return {
        "id": as_str(raw.get("id")) or uuid.uuid4().hex[:8],
        "keywords": cleaned,
        "match": match,
        "reply": reply,
        "enabled": as_bool(raw.get("enabled"), True),
        "cooldown": as_int(raw.get("cooldown"), 0, minimum=0, maximum=86400),
        "created_at": as_int(raw.get("created_at"), 0, minimum=0),
    }


def _normalize_rules(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    rules = []
    for item in raw[:MAX_RULES_PER_SCOPE]:
        rule = _normalize_rule(item)
        if rule:
            rules.append(rule)
    return rules


def _normalize_config(raw: Any) -> Dict[str, Any]:
    config = _default_config()
    if not isinstance(raw, dict):
        return config

    config["global_rules"] = _normalize_rules(raw.get("global_rules"))
    config["default_cooldown"] = as_int(raw.get("default_cooldown"), 10, minimum=0, maximum=3600)

    groups = raw.get("groups")
    if isinstance(groups, dict):
        for group_id, group_data in groups.items():
            try:
                key = str(int(group_id))
            except (TypeError, ValueError):
                continue
            rules = _normalize_rules(
                group_data.get("rules") if isinstance(group_data, dict) else group_data
            )
            group_config: Dict[str, Any] = {"rules": rules}
            if isinstance(group_data, dict) and "default_cooldown" in group_data:
                group_config["default_cooldown"] = as_int(
                    group_data.get("default_cooldown"),
                    config["default_cooldown"],
                    minimum=0,
                    maximum=3600,
                )
            if rules or "default_cooldown" in group_config:
                config["groups"][key] = group_config

    return config


_store = JsonStore(CONFIG_FILE, _default_config, _normalize_config)


def _compile(rule: Dict[str, Any]) -> Optional[List[re.Pattern]]:
    """正则规则预编译；非法正则直接判为不可用。"""
    if rule["match"] != MATCH_REGEX:
        return None
    patterns = []
    for keyword in rule["keywords"]:
        try:
            patterns.append(re.compile(keyword, re.IGNORECASE))
        except re.error:
            continue
    return patterns


def is_valid_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def get_config() -> Dict[str, Any]:
    return _store.load()


def get_group_rules(group_id: int) -> List[Dict[str, Any]]:
    config = _store.load()
    group = config["groups"].get(str(int(group_id)))
    return list(group["rules"]) if isinstance(group, dict) else []


def get_global_rules() -> List[Dict[str, Any]]:
    return list(_store.load()["global_rules"])


def get_effective_rules(group_id: int) -> List[Dict[str, Any]]:
    """本群实际生效的规则：群级在前（优先命中），全局在后。"""
    group_rules = [{**rule, "scope": "group"} for rule in get_group_rules(group_id)]
    global_rules = [{**rule, "scope": "global"} for rule in get_global_rules()]
    return group_rules + global_rules


def add_rule(
    keyword: str,
    reply: str,
    group_id: Optional[int] = None,
    match: str = MATCH_CONTAINS,
    cooldown: int = 0,
) -> Optional[Dict[str, Any]]:
    """新增一条规则。关键词重复时返回 None。"""
    keyword = as_str(keyword)
    reply = as_str(reply)
    if not keyword or not reply:
        return None
    if len(keyword) > MAX_KEYWORD_LENGTH or len(reply) > MAX_REPLY_LENGTH:
        return None
    if match not in MATCH_MODES:
        return None
    if match == MATCH_REGEX and not is_valid_regex(keyword):
        return None

    new_rule = {
        "id": uuid.uuid4().hex[:8],
        "keywords": [keyword],
        "match": match,
        "reply": reply,
        "enabled": True,
        "cooldown": max(0, int(cooldown)),
        "created_at": int(time.time()),
    }

    def mutate(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if group_id is None:
            bucket = config["global_rules"]
        else:
            bucket = config["groups"].setdefault(str(int(group_id)), {"rules": []})["rules"]

        target = keyword.casefold()
        if any(
            target == existing.casefold()
            for rule in bucket
            for existing in rule["keywords"]
        ):
            return None
        if len(bucket) >= MAX_RULES_PER_SCOPE:
            return None

        bucket.append(new_rule)
        return new_rule

    return _store.mutate(mutate)


def remove_rule(keyword: str, group_id: Optional[int] = None) -> bool:
    """按关键词或规则 ID 删除。"""
    target = as_str(keyword)
    folded = target.casefold()

    def mutate(config: Dict[str, Any]) -> bool:
        if group_id is None:
            bucket = config["global_rules"]
        else:
            group = config["groups"].get(str(int(group_id)))
            if not group:
                return False
            bucket = group["rules"]

        for index, rule in enumerate(bucket):
            if (
                any(folded == existing.casefold() for existing in rule["keywords"])
                or folded == str(rule["id"]).casefold()
            ):
                bucket.pop(index)
                return True
        return False

    return bool(_store.mutate(mutate))


def find_rule(keyword: str, group_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    bucket = get_global_rules() if group_id is None else get_group_rules(group_id)
    target = as_str(keyword)
    folded = target.casefold()
    for rule in bucket:
        if (
            any(folded == existing.casefold() for existing in rule["keywords"])
            or folded == str(rule["id"]).casefold()
        ):
            return rule
    return None


def update_rule(keyword: str, group_id: Optional[int], **changes: Any) -> bool:
    """修改规则的 match / enabled / cooldown / reply。"""
    target = as_str(keyword)
    folded = target.casefold()
    allowed = {"match", "enabled", "cooldown", "reply"}

    def mutate(config: Dict[str, Any]) -> bool:
        if group_id is None:
            bucket = config["global_rules"]
        else:
            group = config["groups"].get(str(int(group_id)))
            if not group:
                return False
            bucket = group["rules"]

        for rule in bucket:
            if (
                all(folded != existing.casefold() for existing in rule["keywords"])
                and folded != str(rule["id"]).casefold()
            ):
                continue
            for key, value in changes.items():
                if key in allowed:
                    rule[key] = value
            return True
        return False

    return bool(_store.mutate(mutate))


def match_rules(text: str, group_id: int) -> Optional[Dict[str, Any]]:
    """返回第一条命中的规则；没有命中返回 None。

    群级规则先于全局规则被检查，这样某个群可以用同名关键词覆盖全局回复。
    """
    if not text:
        return None

    candidate = text.strip()
    if len(candidate) > MAX_MATCH_LENGTH:
        return None

    lowered = candidate.lower()

    for rule in get_effective_rules(group_id):
        if not rule.get("enabled", True):
            continue

        mode = rule["match"]
        if mode == MATCH_REGEX:
            for pattern in _compile(rule) or []:
                if pattern.search(candidate):
                    return rule
            continue

        for keyword in rule["keywords"]:
            needle = keyword.lower()
            if mode == MATCH_EXACT and lowered == needle:
                return rule
            if mode == MATCH_PREFIX and lowered.startswith(needle):
                return rule
            if mode == MATCH_CONTAINS and needle in lowered:
                return rule

    return None


def get_default_cooldown(group_id: Optional[int] = None) -> int:
    """取默认冷却；群级设置优先，未配置时回退到全局默认。"""
    config = _store.load()
    if group_id is not None:
        group = config["groups"].get(str(int(group_id)))
        if isinstance(group, dict) and "default_cooldown" in group:
            return int(group["default_cooldown"])
    return int(config["default_cooldown"])


def set_default_cooldown(seconds: int, group_id: Optional[int] = None) -> bool:
    """设置默认冷却。``group_id`` 非空时只影响该群。"""
    value = max(0, min(3600, int(seconds)))

    def mutate(config: Dict[str, Any]) -> bool:
        if group_id is None:
            if config["default_cooldown"] == value:
                return False
            config["default_cooldown"] = value
            return True

        group = config["groups"].setdefault(str(int(group_id)), {"rules": []})
        if group.get("default_cooldown") == value:
            return False
        group["default_cooldown"] = value
        return True

    return bool(_store.mutate(mutate))


def media_path(name: str) -> str:
    return os.path.join(MEDIA_DIR, os.path.basename(name))


__all__ = [
    "MATCH_MODES", "MATCH_LABELS", "MATCH_CONTAINS", "MATCH_EXACT", "MATCH_PREFIX", "MATCH_REGEX",
    "MEDIA_DIR", "MAX_MATCH_LENGTH",
    "get_config", "get_group_rules", "get_global_rules", "get_effective_rules",
    "add_rule", "remove_rule", "find_rule", "update_rule", "match_rules",
    "get_default_cooldown", "set_default_cooldown", "is_valid_regex", "media_path",
]
