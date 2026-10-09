"""Bounded retrieval and in-memory caching for QQ group avatars."""
from __future__ import annotations

import asyncio
import time
import warnings
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Optional

import httpx
from PIL import Image

AVATAR_MAX_BYTES = 256 * 1024
AVATAR_CACHE_ENTRIES = 64
AVATAR_CACHE_TTL_SECONDS = 60 * 60
AVATAR_FETCH_CONCURRENCY = 4
AVATAR_FETCH_QUEUE_TIMEOUT_SECONDS = 2.0
AVATAR_FETCH_TOTAL_TIMEOUT_SECONDS = 6.0

_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}


class AvatarUnavailable(Exception):
    """The fixed avatar resource could not be retrieved safely."""


@dataclass(frozen=True)
class GroupAvatar:
    content: bytes
    media_type: str


def _validated_avatar(content: bytes) -> GroupAvatar:
    if not content:
        raise AvatarUnavailable
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                media_type = _MIME_BY_FORMAT.get((image.format or "").upper())
                if media_type is None:
                    raise AvatarUnavailable
                image.verify()
    except AvatarUnavailable:
        raise
    except Exception:
        raise AvatarUnavailable from None
    return GroupAvatar(content=content, media_type=media_type)


class GroupAvatarCache:
    """Fetch fixed QQ group-avatar URLs with strict resource bounds."""

    def __init__(
        self,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._entries: OrderedDict[int, tuple[float, GroupAvatar]] = OrderedDict()
        self._slots = asyncio.Semaphore(AVATAR_FETCH_CONCURRENCY)

    def _get_cached(self, group_id: int) -> Optional[GroupAvatar]:
        cached = self._entries.get(group_id)
        if cached is None:
            return None
        expires_at, avatar = cached
        if expires_at <= self._clock():
            self._entries.pop(group_id, None)
            return None
        self._entries.move_to_end(group_id)
        return avatar

    def _store(self, group_id: int, avatar: GroupAvatar) -> None:
        self._entries[group_id] = (
            self._clock() + AVATAR_CACHE_TTL_SECONDS,
            avatar,
        )
        self._entries.move_to_end(group_id)
        while len(self._entries) > AVATAR_CACHE_ENTRIES:
            self._entries.popitem(last=False)

    async def get(self, group_id: int) -> GroupAvatar:
        cached = self._get_cached(group_id)
        if cached is not None:
            return cached

        try:
            await asyncio.wait_for(
                self._slots.acquire(),
                timeout=AVATAR_FETCH_QUEUE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise AvatarUnavailable from None

        try:
            cached = self._get_cached(group_id)
            if cached is not None:
                return cached
            try:
                avatar = await asyncio.wait_for(
                    self._download(group_id),
                    timeout=AVATAR_FETCH_TOTAL_TIMEOUT_SECONDS,
                )
            except (asyncio.TimeoutError, httpx.HTTPError, OSError, AvatarUnavailable):
                raise AvatarUnavailable from None
            self._store(group_id, avatar)
            return avatar
        finally:
            self._slots.release()

    async def _download(self, group_id: int) -> GroupAvatar:
        url = f"https://p.qlogo.cn/gh/{group_id}/{group_id}/100"
        timeout = httpx.Timeout(4.0, connect=3.0)
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=0)
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise AvatarUnavailable
                length = response.headers.get("content-length")
                if length is not None:
                    try:
                        if int(length) > AVATAR_MAX_BYTES:
                            raise AvatarUnavailable
                    except ValueError:
                        raise AvatarUnavailable from None
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > AVATAR_MAX_BYTES:
                        raise AvatarUnavailable
                    content.extend(chunk)
        return _validated_avatar(bytes(content))
