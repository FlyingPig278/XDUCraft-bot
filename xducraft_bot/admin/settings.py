"""Runtime settings for the loopback-only administration server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

DEFAULT_PORT = 8765
MIN_PASSWORD_LENGTH = 12


class WebAdminSettingsError(RuntimeError):
    """A configuration error safe to report without including configuration values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WebAdminSettings:
    enabled: bool = False
    port: int = DEFAULT_PORT
    password: str = ""


def _config_value(config: Any, name: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(name, default)
    return getattr(config, name, default)


def _parse_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise WebAdminSettingsError("web_admin_enabled_invalid")


def _parse_port(value: Any) -> int:
    if isinstance(value, bool):
        raise WebAdminSettingsError("web_admin_port_invalid")
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise WebAdminSettingsError("web_admin_port_invalid") from None
    if not 1 <= port <= 65535:
        raise WebAdminSettingsError("web_admin_port_invalid")
    return port


def load_settings(driver_config: Optional[Any] = None) -> WebAdminSettings:
    """Load panel settings, with process environment taking precedence.

    The password intentionally has no NoneBot/.env fallback.  It must be present in
    the process environment so NoneBot's global configuration cannot expose it.
    The password is only required when the panel is enabled.
    """

    if "WEB_ADMIN_ENABLED" in os.environ:
        enabled_value: Any = os.environ["WEB_ADMIN_ENABLED"]
    else:
        enabled_value = _config_value(driver_config, "web_admin_enabled", False)
    enabled = _parse_enabled(enabled_value)

    if "WEB_ADMIN_PORT" in os.environ:
        port_value: Any = os.environ["WEB_ADMIN_PORT"]
    else:
        port_value = _config_value(driver_config, "web_admin_port", DEFAULT_PORT)
    try:
        port = _parse_port(port_value)
    except WebAdminSettingsError:
        if enabled:
            raise
        port = DEFAULT_PORT

    if not enabled:
        return WebAdminSettings(port=port)

    password = os.environ.get("WEB_ADMIN_PASSWORD", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WebAdminSettingsError("web_admin_password_invalid")

    return WebAdminSettings(enabled=True, port=port, password=password)


__all__ = [
    "DEFAULT_PORT",
    "MIN_PASSWORD_LENGTH",
    "WebAdminSettings",
    "WebAdminSettingsError",
    "load_settings",
]
