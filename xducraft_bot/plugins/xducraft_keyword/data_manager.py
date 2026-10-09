"""关键词回复的配置存储。

规则同时支持**群级**和**全局**两层：全局规则（如“新手教程”）在所有启用的群里
都生效，群级规则只在本群生效；同一关键词命中时群级优先。

回复内容按消息列表保存，每条消息以 CQ 码字符串表示。图片会在**添加时**下载到
本地——预设回复是长期使用的，直接存 QQ 的临时 URL 过几天就会变成裂图。
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
MAX_REPLIES_PER_TRIGGER = 8
MAX_RULES_PER_SCOPE = 200


def _default_config() -> Dict[str, Any]:
    return {
        "global_rules": [],
        "groups": {},
        # 同一条规则在同一个群里的最小触发间隔（秒），防刷屏。
        "default_cooldown": 10,
    }


def _normalize_replies(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []

    replies = []
    for item in raw[:MAX_REPLIES_PER_TRIGGER]:
        reply = as_str(item)[:MAX_REPLY_LENGTH]
        if reply:
            replies.append(reply)
    return replies


def _normalize_rule(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    keywords = raw.get("keywords")
    if not isinstance(keywords, list):
        return None

    cleaned = []
    for keyword in keywords:
        text = as_str(keyword)[:MAX_KEYWORD_LENGTH]
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        return None

    replies = _normalize_replies(raw.get("replies"))
    if not replies:
        return None

    match = as_str(raw.get("match"), MATCH_CONTAINS).lower()
    if match not in MATCH_MODES:
        match = MATCH_CONTAINS

    return {
        "id": as_str(raw.get("id")) or uuid.uuid4().hex[:8],
        "keywords": cleaned,
        "match": match,
        "replies": replies,
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
            if not isinstance(group_data, dict):
                continue
            rules = _normalize_rules(group_data.get("rules"))
            join_replies = _normalize_replies(group_data.get("join_replies"))
            group_config: Dict[str, Any] = {"rules": rules}
            if join_replies:
                group_config["join_replies"] = join_replies
            if "default_cooldown" in group_data:
                group_config["default_cooldown"] = as_int(
                    group_data.get("default_cooldown"),
                    config["default_cooldown"],
                    minimum=0,
                    maximum=3600,
                )
            if rules or join_replies or "default_cooldown" in group_config:
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


def get_join_replies(group_id: int) -> List[str]:
    """返回本群的入群欢迎消息；未配置时返回空列表。"""
    group = _store.load()["groups"].get(str(int(group_id)))
    if not isinstance(group, dict):
        return []
    return list(group.get("join_replies", []))

_RULE_INPUT_KEYS = frozenset(
    {"id", "keywords", "match", "enabled", "cooldown", "replies"}
)


def export_scope_config(group_id: Optional[int]) -> Dict[str, Any]:
    """导出一个群或全局规则 scope 的完整可编辑配置。"""
    config = _store.load()
    if group_id is None:
        return {
            "rules": list(config["global_rules"]),
            "default_cooldown": int(config["default_cooldown"]),
        }

    group_key = str(int(group_id))
    group = config["groups"].get(group_key)
    if not isinstance(group, dict):
        return {
            "rules": [],
            "join_replies": [],
            "default_cooldown": None,
        }
    return {
        "rules": list(group.get("rules", [])),
        "join_replies": list(group.get("join_replies", [])),
        "default_cooldown": (
            int(group["default_cooldown"])
            if "default_cooldown" in group
            else None
        ),
    }


def _validate_reply_list(raw: Any, *, allow_empty: bool) -> List[str]:
    if not isinstance(raw, list):
        raise ValueError("replies_must_be_array")
    if len(raw) > MAX_REPLIES_PER_TRIGGER:
        raise ValueError("too_many_replies")
    if not allow_empty and not raw:
        raise ValueError("replies_required")

    replies: List[str] = []
    for value in raw:
        if not isinstance(value, str):
            raise ValueError("reply_must_be_string")
        reply = as_str(value)
        if not reply:
            raise ValueError("reply_must_not_be_empty")
        if len(reply) > MAX_REPLY_LENGTH:
            raise ValueError("reply_too_long")
        replies.append(reply)
    return replies


def _validate_scope_payload(
    group_id: Optional[int],
    data: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str], Optional[int]]:
    if not isinstance(data, dict):
        raise ValueError("scope_config_must_be_object")

    expected = (
        {"rules", "default_cooldown"}
        if group_id is None
        else {"rules", "join_replies", "default_cooldown"}
    )
    if set(data) != expected:
        raise ValueError("invalid_scope_config_fields")

    raw_rules = data["rules"]
    if not isinstance(raw_rules, list):
        raise ValueError("rules_must_be_array")
    if len(raw_rules) > MAX_RULES_PER_SCOPE:
        raise ValueError("too_many_rules")

    rules: List[Dict[str, Any]] = []
    seen_keywords: set[str] = set()
    seen_ids: set[str] = set()
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict) or set(raw_rule) != _RULE_INPUT_KEYS:
            raise ValueError("invalid_rule_fields")

        raw_id = raw_rule["id"]
        if raw_id is None:
            rule_id: Optional[str] = None
        elif isinstance(raw_id, str) and as_str(raw_id):
            rule_id = as_str(raw_id)
            if rule_id in seen_ids:
                raise ValueError("duplicate_rule_id")
            seen_ids.add(rule_id)
        else:
            raise ValueError("invalid_rule_id")

        raw_keywords = raw_rule["keywords"]
        if not isinstance(raw_keywords, list) or not raw_keywords:
            raise ValueError("keywords_required")
        keywords: List[str] = []
        for raw_keyword in raw_keywords:
            if not isinstance(raw_keyword, str):
                raise ValueError("keyword_must_be_string")
            keyword = as_str(raw_keyword)
            if not keyword:
                raise ValueError("keyword_must_not_be_empty")
            if len(keyword) > MAX_KEYWORD_LENGTH:
                raise ValueError("keyword_too_long")
            folded = keyword.casefold()
            if folded in seen_keywords:
                raise ValueError("duplicate_keyword")
            seen_keywords.add(folded)
            keywords.append(keyword)

        match = raw_rule["match"]
        if match not in MATCH_MODES:
            raise ValueError("invalid_match_mode")
        if match == MATCH_REGEX and any(
            not is_valid_regex(keyword) for keyword in keywords
        ):
            raise ValueError("invalid_regex")

        enabled = raw_rule["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError("enabled_must_be_boolean")

        cooldown = raw_rule["cooldown"]
        if (
            isinstance(cooldown, bool)
            or not isinstance(cooldown, int)
            or not 0 <= cooldown <= 86400
        ):
            raise ValueError("invalid_rule_cooldown")

        rules.append(
            {
                "id": rule_id,
                "keywords": keywords,
                "match": match,
                "enabled": enabled,
                "cooldown": cooldown,
                "replies": _validate_reply_list(
                    raw_rule["replies"],
                    allow_empty=False,
                ),
            }
        )

    join_replies = (
        []
        if group_id is None
        else _validate_reply_list(data["join_replies"], allow_empty=True)
    )
    default_cooldown = data["default_cooldown"]
    if group_id is not None and default_cooldown is None:
        return rules, join_replies, None
    if (
        isinstance(default_cooldown, bool)
        or not isinstance(default_cooldown, int)
        or not 0 <= default_cooldown <= 3600
    ):
        raise ValueError("invalid_default_cooldown")
    return rules, join_replies, default_cooldown


def replace_scope_config(
    group_id: Optional[int],
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """严格校验并在一次 mutate 中完整替换一个规则 scope。"""
    if group_id is not None and int(group_id) <= 0:
        raise ValueError("invalid_group_id")
    rules, join_replies, default_cooldown = _validate_scope_payload(
        group_id,
        data,
    )
    group_key = str(int(group_id)) if group_id is not None else None

    def mutate(config: Dict[str, Any]) -> Dict[str, Any]:
        if group_key is None:
            old_rules = config["global_rules"]
        else:
            old_group = config["groups"].get(group_key)
            old_rules = (
                old_group.get("rules", [])
                if isinstance(old_group, dict)
                else []
            )

        existing_by_id: Dict[str, Dict[str, Any]] = {}
        all_existing_ids: set[str] = set()
        for old_rule in old_rules:
            old_id = str(old_rule.get("id", ""))
            if not old_id:
                continue
            if old_id in existing_by_id:
                raise ValueError("ambiguous_existing_rule_id")
            existing_by_id[old_id] = old_rule
            all_existing_ids.add(old_id)

        used_ids = set(all_existing_ids)
        replacement: List[Dict[str, Any]] = []
        now = int(time.time())
        for rule in rules:
            rule_id = rule["id"]
            if rule_id is None:
                for _ in range(100):
                    rule_id = uuid.uuid4().hex[:8]
                    if rule_id not in used_ids:
                        break
                else:
                    raise ValueError("rule_id_generation_failed")
                created_at = now
            else:
                old_rule = existing_by_id.get(rule_id)
                if old_rule is None:
                    raise ValueError("unknown_rule_id")
                created_at = int(old_rule.get("created_at", 0))
            used_ids.add(rule_id)
            replacement.append(
                {
                    **rule,
                    "id": rule_id,
                    "created_at": created_at,
                }
            )

        if group_key is None:
            config["global_rules"] = replacement
            config["default_cooldown"] = default_cooldown
            return {
                "rules": replacement,
                "default_cooldown": default_cooldown,
            }

        group: Dict[str, Any] = {"rules": replacement}
        if join_replies:
            group["join_replies"] = join_replies
        if default_cooldown is not None:
            group["default_cooldown"] = default_cooldown

        if replacement or join_replies or default_cooldown is not None:
            config["groups"][group_key] = group
        else:
            config["groups"].pop(group_key, None)
        return {
            "rules": replacement,
            "join_replies": join_replies,
            "default_cooldown": default_cooldown,
        }

    return _store.mutate(mutate)



def add_rule(
    keyword: str,
    replies: Sequence[str],
    group_id: Optional[int] = None,
    match: str = MATCH_CONTAINS,
    cooldown: int = 0,
) -> Optional[Dict[str, Any]]:
    """新增一条规则。关键词重复或回复不合法时返回 None。"""
    keyword = as_str(keyword)
    if isinstance(replies, (str, bytes)):
        return None
    reply_list = list(replies)
    cleaned_replies = [as_str(reply) for reply in reply_list]
    if not keyword or not cleaned_replies:
        return None
    if (
        len(keyword) > MAX_KEYWORD_LENGTH
        or len(cleaned_replies) > MAX_REPLIES_PER_TRIGGER
        or any(not reply or len(reply) > MAX_REPLY_LENGTH for reply in cleaned_replies)
    ):
        return None
    if match not in MATCH_MODES:
        return None
    if match == MATCH_REGEX and not is_valid_regex(keyword):
        return None

    new_rule = {
        "id": uuid.uuid4().hex[:8],
        "keywords": [keyword],
        "match": match,
        "replies": cleaned_replies,
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
    """修改规则的 match / enabled / cooldown / replies。"""
    target = as_str(keyword)
    folded = target.casefold()
    allowed = {"match", "enabled", "cooldown", "replies"}

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


def set_join_replies(group_id: int, replies: Sequence[str]) -> bool:
    """设置本群入群欢迎消息；内容不合法时不写入。"""
    if isinstance(replies, (str, bytes)):
        return False
    reply_list = list(replies)
    cleaned_replies = [as_str(reply) for reply in reply_list]
    if (
        not cleaned_replies
        or len(cleaned_replies) > MAX_REPLIES_PER_TRIGGER
        or any(not reply or len(reply) > MAX_REPLY_LENGTH for reply in cleaned_replies)
    ):
        return False

    def mutate(config: Dict[str, Any]) -> bool:
        group = config["groups"].setdefault(str(int(group_id)), {"rules": []})
        if group.get("join_replies", []) == cleaned_replies:
            return False
        group["join_replies"] = cleaned_replies
        return True

    return bool(_store.mutate(mutate))


def clear_join_replies(group_id: int) -> bool:
    """清除本群入群欢迎消息。"""
    def mutate(config: Dict[str, Any]) -> bool:
        group = config["groups"].get(str(int(group_id)))
        if not isinstance(group, dict) or "join_replies" not in group:
            return False
        del group["join_replies"]
        return True

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
    "MEDIA_DIR", "MAX_MATCH_LENGTH", "MAX_KEYWORD_LENGTH", "MAX_REPLY_LENGTH",
    "MAX_REPLIES_PER_TRIGGER", "MAX_RULES_PER_SCOPE",
    "get_config", "get_group_rules", "get_global_rules", "get_effective_rules",
    "get_join_replies", "set_join_replies", "clear_join_replies",
    "export_scope_config", "replace_scope_config",
    "add_rule", "remove_rule", "find_rule", "update_rule", "match_rules",
    "get_default_cooldown", "set_default_cooldown", "is_valid_regex", "media_path",
]
