"""Strict transport-only models for the declarative administration API."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Switch(Input):
    enabled: StrictBool


class Patch(Input):
    set: Dict[str, Any]
    unset: List[StrictStr]

def positive_id(value: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError("invalid_id")
    number = int(value)
    if number <= 0:
        raise ValueError("invalid_id")
    return number


__all__ = ["Input", "Patch", "Switch", "positive_id"]
