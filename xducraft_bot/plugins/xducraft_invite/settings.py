"""邀请码插件的部署期配置。"""

from __future__ import annotations

from dataclasses import dataclass

from nonebot.log import logger
from pydantic import BaseModel

from . import texts as text

DEFAULT_API_URL = "https://www.xducraft.cn/api/invitation-codes/generate"


class Config(BaseModel):
    """字段名对应 ``.env`` 中的同名大写配置。"""

    invite_group_id: int = 0
    invite_api_url: str = DEFAULT_API_URL
    invite_api_secret: str = ""


@dataclass(frozen=True)
class InviteSettings:
    group_id: int = 0
    api_url: str = DEFAULT_API_URL
    api_secret: str = ""

    def configuration_error(self) -> str:
        if self.group_id <= 0:
            return text.CONFIG_GROUP_ID_MISSING
        if not self.api_secret:
            return text.CONFIG_SECRET_MISSING
        if not self.api_url.lower().startswith("https://"):
            return text.CONFIG_HTTPS_REQUIRED
        return ""


def load() -> InviteSettings:
    config = Config()
    try:
        import nonebot

        config = nonebot.get_plugin_config(Config)
    except Exception as exc:
        logger.opt(exception=False).debug("[Invite] 读取配置失败（{}），使用空配置。", exc)

    return InviteSettings(
        group_id=int(config.invite_group_id or 0),
        api_url=str(config.invite_api_url or DEFAULT_API_URL).strip(),
        api_secret=str(config.invite_api_secret or ""),
    )


SETTINGS = load()


__all__ = ["Config", "InviteSettings", "SETTINGS", "DEFAULT_API_URL", "load"]
