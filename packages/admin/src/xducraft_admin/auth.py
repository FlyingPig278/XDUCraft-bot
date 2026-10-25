"""In-memory authentication for the local administration panel."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

SESSION_LIFETIME_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class _Session:
    csrf_token: str
    expires_at: int


class AdminAuth:
    """Own independent browser sessions for one administrator password."""

    def __init__(
        self,
        password: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._password = password.encode("utf-8")
        self._clock = clock
        self._sessions: Dict[str, _Session] = {}

    def _now(self) -> float:
        return float(self._clock())

    def _purge_expired(self, now: float) -> None:
        expired = [
            token
            for token, record in self._sessions.items()
            if now >= record.expires_at
        ]
        for token in expired:
            self._sessions.pop(token, None)

    @staticmethod
    def _public(record: _Session) -> Dict[str, object]:
        return {
            "authenticated": True,
            "csrf_token": record.csrf_token,
            "expires_at": record.expires_at,
        }

    def login(self, password: str) -> Optional[Dict[str, object]]:
        """Create a session, or return ``None`` when the password does not match.

        ``session_token`` is transport metadata: the HTTP layer must remove it from
        the JSON response and place it in the HttpOnly session cookie.
        """

        now = self._now()
        self._purge_expired(now)
        if not isinstance(password, str):
            return None
        try:
            candidate = password.encode("utf-8")
        except UnicodeEncodeError:
            return None
        if not secrets.compare_digest(candidate, self._password):
            return None

        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        record = _Session(
            csrf_token=csrf_token,
            expires_at=int(now) + SESSION_LIFETIME_SECONDS,
        )
        self._sessions[session_token] = record
        result = self._public(record)
        result["session_token"] = session_token
        return result

    def session(self, token: Optional[str]) -> Optional[Dict[str, object]]:
        """Return public session data for a live token."""

        now = self._now()
        self._purge_expired(now)
        if not token:
            return None
        record = self._sessions.get(token)
        if record is None:
            return None
        return self._public(record)

    def logout(self, token: Optional[str]) -> None:
        """Invalidate one browser session."""

        self._purge_expired(self._now())
        if token:
            self._sessions.pop(token, None)

    def verify_csrf(self, token: Optional[str], csrf: Optional[str]) -> bool:
        """Verify a CSRF token for a live browser session."""

        now = self._now()
        self._purge_expired(now)
        if not token or not isinstance(csrf, str):
            return False
        record = self._sessions.get(token)
        if record is None:
            return False
        try:
            supplied = csrf.encode("utf-8")
            expected = record.csrf_token.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return secrets.compare_digest(supplied, expected)


__all__ = ["AdminAuth", "SESSION_LIFETIME_SECONDS"]
