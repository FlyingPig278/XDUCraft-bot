"""Strict public resource schemas; validation never echoes submitted values."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Switch(Input):
    enabled: StrictBool


class Happy(Input):
    emoji_id: Optional[StrictStr]


class Server(Input):
    ip: StrictStr
    comment: StrictStr = ""
    tag: StrictStr = ""
    tag_color: StrictStr = ""
    ignore_in_list: StrictBool = False
    hide_ip: StrictBool = False
    display_name: StrictStr = ""
    auth_mode: Literal["", "official", "mua", "xdu", "yggdrasil", "offline", "mixed"] = ""
    priority: Optional[StrictInt] = None
    children: List[Server] = Field(default_factory=list)


class MCGlobal(Input):
    status_api_source: Literal["protocol", "sjtu", "jsu", "custom", "auto", "auto_api_first"]
    status_api_url: StrictStr


class MCGroup(Input):
    servers: List[Server]
    footer: StrictStr
    show_offline_by_default: StrictBool
    status_api_source: Literal["", "protocol", "sjtu", "jsu", "custom", "auto", "auto_api_first"]
    status_api_url: StrictStr
    default_auth_mode: Literal["", "official", "mua", "xdu", "yggdrasil", "offline", "mixed"]
    auth_detect: StrictBool
    quiet_admin_replies: StrictBool


class Wordcloud(Input):
    ban_user_ids: List[StrictStr]
    min_word_length: StrictInt = Field(ge=1)
    max_words: StrictInt = Field(ge=20)
    retention_days: StrictInt = Field(ge=30)
    additional_stopwords: List[StrictStr]
    footer_subtitle: StrictStr
    footer_branding_enabled: StrictBool
    footer_branding_text: StrictStr


class AntiRecall(Input):
    cache_retention_hours: StrictInt = Field(ge=1, le=720)
    recall_retention_days: StrictInt = Field(ge=1, le=365)
    max_query_results: StrictInt = Field(ge=1, le=100)
    save_media: StrictBool
    max_media_mb: StrictInt = Field(ge=1, le=200)
    include_self: StrictBool
    exempt_user_ids: List[StrictStr]


class Pig(Input):
    max_forward_results: StrictInt = Field(ge=1)


class Rule(Input):
    id: Optional[StrictStr]
    keywords: List[StrictStr]
    match: Literal["contains", "exact", "prefix", "regex"]
    enabled: StrictBool
    cooldown: StrictInt = Field(ge=0, le=86400)
    replies: List[List[Dict[str, Any]]]


class KeywordGlobal(Input):
    rules: List[Rule] = Field(max_length=200)
    default_cooldown: StrictInt = Field(ge=0, le=3600)


class KeywordGroup(Input):
    rules: List[Rule] = Field(max_length=200)
    join_replies: List[List[Dict[str, Any]]] = Field(max_length=8)
    default_cooldown: Optional[StrictInt] = Field(ge=0, le=3600)


class Deployment(Input):
    set: Dict[str, Any]
    unset: List[StrictStr]


def positive_id(value: str, *, allow_zero: bool = False) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise ValueError("invalid_id")
    number = int(value)
    if number < (0 if allow_zero else 1):
        raise ValueError("invalid_id")
    return number
