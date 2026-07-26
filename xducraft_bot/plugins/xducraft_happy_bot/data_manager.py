"""贴表情回应的配置。

支持按群设置不同的表情，未单独设置的群走全局默认值。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from xducraft_bot.shared.json_store import JsonStore, as_str

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "emoji_like_config.json")
DEFAULT_EMOJI_ID = "123"


def _default_data() -> Dict[str, Any]:
    return {"emoji_id": DEFAULT_EMOJI_ID, "groups": {}}


def _clean_emoji_id(value: Any, fallback: str = DEFAULT_EMOJI_ID) -> str:
    text = as_str(value)
    return text if text.isdigit() else fallback


def _normalize(raw: Any) -> Dict[str, Any]:
    data = _default_data()
    if not isinstance(raw, dict):
        return data

    data["emoji_id"] = _clean_emoji_id(raw.get("emoji_id"))

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

    return data


_store = JsonStore(DATA_FILE, _default_data, _normalize)


def get_emoji_id(group_id: Optional[int] = None) -> str:
    """取某个群生效的表情 ID；没有群级配置时回退到全局默认。"""
    data = _store.load()
    if group_id is not None:
        group_value = data["groups"].get(str(int(group_id)))
        if group_value:
            return group_value
    return _clean_emoji_id(data.get("emoji_id"))


def set_emoji_id(emoji_id: str, group_id: Optional[int] = None) -> None:
    """设置表情 ID。``group_id`` 为 None 时设置的是全局默认值。"""
    value = as_str(emoji_id)
    if not value.isdigit():
        raise ValueError("emoji_id 必须是纯数字")

    def mutate(data: Dict[str, Any]) -> bool:
        if group_id is None:
            data["emoji_id"] = value
        else:
            data["groups"][str(int(group_id))] = value
        return True

    _store.mutate(mutate)


def clear_group_emoji_id(group_id: int) -> bool:
    """清除群级配置，回到全局默认。"""
    def mutate(data: Dict[str, Any]) -> bool:
        return data["groups"].pop(str(int(group_id)), None) is not None

    return bool(_store.mutate(mutate))


__all__ = ["get_emoji_id", "set_emoji_id", "clear_group_emoji_id", "DEFAULT_EMOJI_ID"]
