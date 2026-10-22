"""Independent per-group emoji-reaction configuration."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from xducraft_bot.shared import feature_gate
from xducraft_bot.shared.config_store import ConfigDocumentStore
from xducraft_bot.shared.data_paths import plugin_data_dir
from xducraft_bot.shared.json_store import as_str

DATA_DIR = str(plugin_data_dir("happy_bot", os.path.join(os.path.dirname(__file__), "data")))
DATA_FILE = os.path.join(DATA_DIR, "emoji_like_config.json")
DEFAULT_EMOJI_ID = "123"


def _default_data() -> Dict[str, Any]:
    return {"schema_version": 2, "groups": {}}


def _clean_emoji_id(value: Any, fallback: str = DEFAULT_EMOJI_ID) -> str:
    text = as_str(value)
    return text if text.isdigit() else fallback


def _normalize(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("happy_config_must_be_object")

    data = _default_data()
    legacy_default = _clean_emoji_id(raw.get("emoji_id"))
    groups = raw.get("groups")
    if isinstance(groups, dict):
        for group_id, emoji_id in groups.items():
            try:
                key = str(int(group_id))
            except (TypeError, ValueError):
                continue
            cleaned = _clean_emoji_id(emoji_id, "")
            if cleaned:
                data["groups"][key] = cleaned

    if raw.get("schema_version") != 2:
        for group_id in feature_gate.list_configured_groups():
            data["groups"].setdefault(str(group_id), legacy_default)
    return data


_store = ConfigDocumentStore("happy_bot", _default_data, _normalize, legacy_path=DATA_FILE)


def get_emoji_id(group_id: int) -> str:
    """Return this group's direct value; a fresh group uses the code default."""
    value = _store.load()["groups"].get(str(int(group_id)))
    return _clean_emoji_id(value)


def list_configured_groups() -> List[int]:
    """列出有独立表情设置的正整数群号。"""
    groups: List[int] = []
    for group_key in _store.load()["groups"]:
        try:
            group_id = int(group_key)
        except (TypeError, ValueError):
            continue
        if group_id > 0:
            groups.append(group_id)
    return sorted(set(groups))



def set_emoji_id(emoji_id: str, group_id: int) -> None:
    """Set one group's emoji ID."""
    value = as_str(emoji_id)
    if not value.isdigit():
        raise ValueError("emoji_id 必须是纯数字")

    def mutate(data: Dict[str, Any]) -> bool:
        key = str(int(group_id))
        if data["groups"].get(key) == value:
            return False
        data["groups"][key] = value
        return True

    _store.mutate(mutate)




__all__ = [
    "get_emoji_id",
    "list_configured_groups",
    "set_emoji_id",
    "DEFAULT_EMOJI_ID",
]
