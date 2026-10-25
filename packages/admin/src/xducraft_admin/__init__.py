"""Lifecycle registration for the optional local administration panel."""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Optional

from nonebot import get_driver, require
from nonebot.log import logger
from nonebot.plugin import PluginMetadata

require("xducraft_config")

from xducraft_bot.shared.configuration import PROTOCOL_KEY
from .configuration import DECLARATION

from .settings import (
    WebAdminSettings,
    WebAdminSettingsError,
    load_settings,
)

__plugin_meta__ = PluginMetadata(
    name="XDUCraft_admin",
    description="仅回环监听的 XDUCraft 网页管理面板",
    usage="通过 WEB_ADMIN_ENABLED 启用，并经本机或 SSH 隧道访问。",
    extra={PROTOCOL_KEY: DECLARATION},
)

_DRIVER = get_driver()
_SETTINGS: Optional[WebAdminSettings]
_SETTINGS_ERROR: Optional[str]
try:
    _SETTINGS = load_settings(_DRIVER.config)
    _SETTINGS_ERROR = None
except WebAdminSettingsError as exc:
    _SETTINGS = None
    _SETTINGS_ERROR = exc.code

_stop_server: Optional[Callable[[], Awaitable[None]]] = None


def _static_root() -> Path:
    return Path(__file__).resolve().parent / "static"


@_DRIVER.on_startup
async def _start_admin_panel() -> None:
    """Build the production service only after every plugin has loaded."""

    global _stop_server

    if _SETTINGS_ERROR is not None:
        logger.opt(exception=False).error(
            "[WebAdmin] startup rejected code={}",
            _SETTINGS_ERROR,
        )
        return
    if _SETTINGS is None or not _SETTINGS.enabled:
        return

    try:
        # FastAPI, Uvicorn, and business adapters remain optional unless enabled.
        from .adapters import build_service
        from .app import create_app
        from .auth import AdminAuth
        from .server import start, stop

        service = build_service()
        auth = AdminAuth(_SETTINGS.password)
        application = create_app(service, auth, _static_root())
        await start(application, _SETTINGS.port)
        _stop_server = stop
    except Exception as exc:
        _stop_server = None
        logger.opt(exception=False).error(
            "[WebAdmin] startup failed code=web_admin_startup_failed type={}",
            type(exc).__name__,
        )


@_DRIVER.on_shutdown
async def _stop_admin_panel() -> None:
    global _stop_server

    stop_server = _stop_server
    _stop_server = None
    if stop_server is None:
        return
    try:
        await stop_server()
    except Exception as exc:
        logger.opt(exception=False).error(
            "[WebAdmin] shutdown failed code=web_admin_shutdown_failed type={}",
            type(exc).__name__,
        )
