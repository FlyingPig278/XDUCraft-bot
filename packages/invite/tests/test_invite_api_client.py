from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from xducraft_invite.api_client import InviteApiClient


SECRET = "test-secret"
URL = "https://example.test/api/invitation-codes/generate"
CODE = "0123456789abcdef0123456789abcdef"


def _decrypt_request(request: httpx.Request) -> dict:
    envelope = json.loads(request.content)
    key = hashlib.sha256(SECRET.encode()).digest()
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(envelope["iv"]),
        base64.b64decode(envelope["data"]) + base64.b64decode(envelope["tag"]),
        None,
    )
    return json.loads(plaintext)


def _success_response(request: httpx.Request) -> httpx.Response:
    payload = _decrypt_request(request)
    key = hashlib.sha256(SECRET.encode()).digest()
    iv = bytes(range(12))
    plaintext = json.dumps({
        "code": CODE,
        "description": payload["remark"],
        "generated_at": "2026-08-24 12:00:00",
    }).encode()
    sealed = AESGCM(key).encrypt(iv, plaintext, None)
    return httpx.Response(200, json={
        "iv": base64.b64encode(iv).decode(),
        "data": base64.b64encode(sealed[:-16]).decode(),
        "tag": base64.b64encode(sealed[-16:]).decode(),
    })


@pytest.mark.asyncio
async def test_generate_encrypts_request_and_decrypts_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(_decrypt_request(request))
        return _success_response(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = InviteApiClient(URL, SECRET, http_client=http)
        result = await client.generate("[自助]233333")

    assert captured["remark"] == "[自助]233333"
    assert isinstance(captured["ts"], int)
    assert result.code == CODE
    assert result.description == "[自助]233333"


@pytest.mark.asyncio
async def test_network_error_is_retried_once():
    calls = 0
    sleeps = []
    ivs = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        ivs.append(json.loads(request.content)["iv"])
        if calls == 1:
            raise httpx.ReadTimeout("lost response", request=request)
        return _success_response(request)

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = InviteApiClient(URL, SECRET, http_client=http, sleep=fake_sleep)
        result = await client.generate("[管理员发放]233333")

    assert result.code == CODE
    assert calls == 2
    assert sleeps == [1.0]
    assert len(set(ivs)) == 2


@pytest.mark.asyncio
async def test_rate_limit_waits_for_retry_after_then_retries():
    calls = 0
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.25"}, json={
                "success": False,
                "message": "Too Many Attempts",
            })
        return _success_response(request)

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = InviteApiClient(URL, SECRET, http_client=http, sleep=fake_sleep)
        result = await client.generate("[自助]233333")

    assert result.code == CODE
    assert calls == 2
    assert sleeps == [0.25]
