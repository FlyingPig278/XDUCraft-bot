"""邀请码 API 的 AES-256-GCM 客户端。"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import texts as text

CODE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
IV_SIZE = 12
TAG_SIZE = 16
MAX_RETRY_AFTER = 60.0


class InviteApiError(RuntimeError):
    """API、网络或密文协议错误；消息中永远不包含邀请码。"""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class GeneratedInvite:
    code: str
    description: str
    generated_at: str


class InviteApiClient:
    """复用 HTTP 连接，并严格实现 API 文档定义的信封格式。"""

    def __init__(
        self,
        api_url: str,
        secret: str,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.api_url = str(api_url).strip()
        self._key = hashlib.sha256(str(secret).encode("utf-8")).digest()
        self._sleep = sleep
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    def _encrypt_request(self, remark: str) -> Dict[str, str]:
        clean_remark = str(remark).strip()
        if not clean_remark:
            raise InviteApiError(text.API_REMARK_REQUIRED)
        if len(clean_remark) > 255:
            raise InviteApiError(text.API_REMARK_TOO_LONG)

        plaintext = json.dumps(
            {"remark": clean_remark, "ts": int(time.time())},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        iv = os.urandom(IV_SIZE)
        sealed = AESGCM(self._key).encrypt(iv, plaintext, None)
        data, tag = sealed[:-TAG_SIZE], sealed[-TAG_SIZE:]
        return {
            "iv": base64.b64encode(iv).decode("ascii"),
            "data": base64.b64encode(data).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
        }

    @staticmethod
    def _decode_base64(envelope: Dict[str, object], field: str, expected_size: Optional[int] = None) -> bytes:
        value = envelope.get(field)
        if not isinstance(value, str) or not value:
            raise InviteApiError(text.api_field_missing(field))
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise InviteApiError(text.api_field_not_base64(field)) from exc
        if expected_size is not None and len(decoded) != expected_size:
            raise InviteApiError(text.api_field_wrong_size(field))
        return decoded

    def _decrypt_response(self, response: httpx.Response) -> GeneratedInvite:
        try:
            envelope = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise InviteApiError(text.API_SUCCESS_NOT_JSON, status_code=200) from exc
        if not isinstance(envelope, dict):
            raise InviteApiError(text.API_SUCCESS_NOT_ENVELOPE, status_code=200)

        iv = self._decode_base64(envelope, "iv", IV_SIZE)
        data = self._decode_base64(envelope, "data")
        tag = self._decode_base64(envelope, "tag", TAG_SIZE)
        if not data:
            raise InviteApiError(text.API_CIPHERTEXT_EMPTY, status_code=200)

        try:
            plaintext = AESGCM(self._key).decrypt(iv, data + tag, None)
        except InvalidTag as exc:
            raise InviteApiError(text.API_DECRYPT_FAILED, status_code=200) from exc

        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InviteApiError(text.API_PLAINTEXT_NOT_JSON, status_code=200) from exc
        if not isinstance(payload, dict):
            raise InviteApiError(text.API_PLAINTEXT_NOT_OBJECT, status_code=200)

        code = payload.get("code")
        description = payload.get("description")
        generated_at = payload.get("generated_at")
        if not isinstance(code, str) or CODE_PATTERN.fullmatch(code) is None:
            raise InviteApiError(text.API_CODE_INVALID, status_code=200)
        if not isinstance(description, str) or not isinstance(generated_at, str):
            raise InviteApiError(text.API_METADATA_INCOMPLETE, status_code=200)
        return GeneratedInvite(code=code, description=description, generated_at=generated_at)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return text.api_http_error(response.status_code)
        if isinstance(payload, dict) and isinstance(payload.get("message"), str):
            message = payload["message"].strip()
            if message:
                return message[:300]
        return text.api_http_error(response.status_code)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            seconds = float(response.headers.get("Retry-After", "1"))
        except (TypeError, ValueError):
            seconds = 1.0
        return max(0.0, min(MAX_RETRY_AFTER, seconds))

    async def generate(self, remark: str) -> GeneratedInvite:
        for attempt in range(2):
            # 重试也是一次独立请求，必须重新生成 IV；GCM 下跨请求复用 IV 是安全事故。
            envelope = self._encrypt_request(remark)
            try:
                response = await self._http.post(self.api_url, json=envelope)
            except httpx.TransportError as exc:
                if attempt == 0:
                    await self._sleep(1.0)
                    continue
                raise InviteApiError(text.API_CONNECTION_FAILED) from exc

            if response.status_code == 429 and attempt == 0:
                await self._sleep(self._retry_after(response))
                continue
            if response.status_code != 200:
                raise InviteApiError(
                    self._error_message(response),
                    status_code=response.status_code,
                )
            return self._decrypt_response(response)

        raise InviteApiError(text.API_REQUEST_FAILED)


__all__ = ["GeneratedInvite", "InviteApiClient", "InviteApiError"]
