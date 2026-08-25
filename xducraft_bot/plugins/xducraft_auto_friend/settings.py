"""自动接受好友申请插件的部署配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from nonebot.log import logger
from pydantic import BaseModel, Field


class Config(BaseModel):
    """字段名对应 ``.env`` 中的同名大写配置。"""

    auto_accept_friend_group_ids: List[int] = Field(default_factory=list)


@dataclass(frozen=True)
class AutoFriendSettings:
    """允许自动接受其成员好友申请的群。"""

    group_ids: Tuple[int, ...] = ()


def _normalize_group_ids(group_ids: List[int]) -> Tuple[int, ...]:
    """去掉无效项和重复项，同时保持配置顺序。"""
    return tuple(dict.fromkeys(int(group_id) for group_id in group_ids if int(group_id) > 0))


def load() -> AutoFriendSettings:
    config = Config()
    try:
        import nonebot

        config = nonebot.get_plugin_config(Config)
    except Exception as exc:
        logger.opt(exception=False).debug(
            "[AutoFriend] 读取配置失败（{}），禁用自动接受。", exc
        )

    return AutoFriendSettings(group_ids=_normalize_group_ids(config.auto_accept_friend_group_ids))


SETTINGS = load()


__all__ = ["AutoFriendSettings", "Config", "SETTINGS", "load"]
