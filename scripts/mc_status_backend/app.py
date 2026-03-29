import asyncio
import json
import os
import struct
import time
from contextlib import suppress
from html import escape
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from mcstatus import JavaServer

DEFAULT_SERVER_PORT = 25565
STATUS_QUERY_TIMEOUT = float(os.getenv("MC_STATUS_BACKEND_TIMEOUT", "3.0"))

app = FastAPI(title="XDUCraft MC Status Backend", version="1.0.0")


def _encode_varint(value: int) -> bytes:
    encoded = bytearray()
    if value < 0:
        value = (1 << 32) + value

    while True:
        current = value & 0x7F
        value >>= 7
        if value:
            current |= 0x80
        encoded.append(current)
        if not value:
            break

    return bytes(encoded)


async def _read_varint(reader: asyncio.StreamReader) -> int:
    num_read = 0
    result = 0

    while True:
        current = (await reader.readexactly(1))[0]
        result |= (current & 0x7F) << (7 * num_read)
        num_read += 1

        if num_read > 5:
            raise ValueError("VarInt 过长")
        if (current & 0x80) == 0:
            break

    if result & (1 << 31):
        result -= 1 << 32
    return result


async def _fetch_raw_status_payload(
    connect_host: str,
    connect_port: int,
    handshake_host: str,
    handshake_port: int,
) -> tuple[dict[str, Any], int]:
    started_at = time.perf_counter()
    connection = asyncio.open_connection(connect_host, connect_port)
    reader, writer = await asyncio.wait_for(connection, timeout=STATUS_QUERY_TIMEOUT)

    try:
        host_bytes = handshake_host.encode("utf-8")
        handshake_packet = (
            _encode_varint(0)
            + _encode_varint(-1)
            + _encode_varint(len(host_bytes))
            + host_bytes
            + struct.pack(">H", handshake_port)
            + _encode_varint(1)
        )
        writer.write(_encode_varint(len(handshake_packet)) + handshake_packet)

        request_packet = _encode_varint(0)
        writer.write(_encode_varint(len(request_packet)) + request_packet)
        await asyncio.wait_for(writer.drain(), timeout=STATUS_QUERY_TIMEOUT)

        await asyncio.wait_for(_read_varint(reader), timeout=STATUS_QUERY_TIMEOUT)
        packet_id = await asyncio.wait_for(_read_varint(reader), timeout=STATUS_QUERY_TIMEOUT)
        if packet_id != 0:
            raise ValueError(f"意外的状态包 ID: {packet_id}")

        payload_length = await asyncio.wait_for(_read_varint(reader), timeout=STATUS_QUERY_TIMEOUT)
        payload = await asyncio.wait_for(reader.readexactly(payload_length), timeout=STATUS_QUERY_TIMEOUT)
        latency = int(round((time.perf_counter() - started_at) * 1000))
        return json.loads(payload.decode("utf-8")), latency
    finally:
        writer.close()
        with suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)


def _parse_server_address(address: str) -> tuple[str, int]:
    parsed = urlparse(f"//{address}")
    hostname = parsed.hostname or address
    port = parsed.port or DEFAULT_SERVER_PORT
    return hostname, port


def _component_to_plain_text(component: Any) -> str:
    if component is None:
        return ""

    if isinstance(component, str):
        return component

    if isinstance(component, list):
        return "".join(_component_to_plain_text(item) for item in component)

    if isinstance(component, dict):
        text = str(component.get("text", ""))
        extra = _component_to_plain_text(component.get("extra", []))
        return text + extra

    return str(component)


def _component_to_html(component: Any, inherited_color: str | None = None) -> str:
    if component is None:
        return ""

    if isinstance(component, str):
        return escape(component, quote=True).replace("\n", "<br>")

    if isinstance(component, list):
        return "".join(_component_to_html(item, inherited_color) for item in component)

    if isinstance(component, dict):
        current_color = component.get("color") or inherited_color
        text = escape(str(component.get("text", "")), quote=True).replace("\n", "<br>")
        if current_color and text:
            text = f'<font color="{escape(str(current_color), quote=True)}">{text}</font>'
        extra = _component_to_html(component.get("extra", []), current_color)
        return text + extra

    return escape(str(component), quote=True).replace("\n", "<br>")


def _normalize_description(raw_description: Any) -> dict[str, str]:
    text = _component_to_plain_text(raw_description)
    html = _component_to_html(raw_description)

    normalized: dict[str, str] = {}
    if html:
        normalized["html"] = html
    if text:
        normalized["text"] = text
    return normalized


def _normalize_player_sample(sample: Any) -> list[dict[str, str]]:
    if not sample:
        return []

    normalized_sample: list[dict[str, str]] = []
    for player in sample:
        if isinstance(player, dict):
            player_name = player.get("name")
            player_id = player.get("id")
        else:
            player_name = getattr(player, "name", None)
            player_id = getattr(player, "id", None)

        if not player_name:
            continue

        normalized_player = {"name": str(player_name)}
        if player_id is not None:
            normalized_player["id"] = str(player_id)
        normalized_sample.append(normalized_player)

    return normalized_sample


async def get_single_server_status(query: str) -> dict[str, Any]:
    hostname, port = _parse_server_address(query)
    fallback_response = {
        "online": False,
        "hostname": hostname,
        "port": port,
        "original_query": query,
        "ip": query,
    }

    try:
        connection_candidates: list[tuple[str, int]] = []

        try:
            server = await JavaServer.async_lookup(query, timeout=STATUS_QUERY_TIMEOUT)
            connection_candidates.append((server.address.host, server.address.port))
        except Exception:
            pass

        direct_target = (hostname, port)
        if direct_target not in connection_candidates:
            connection_candidates.append(direct_target)

        attempt_errors: list[str] = []
        raw_status: dict[str, Any] | None = None
        latency: int | None = None
        resolved_host_for_output = hostname
        resolved_port_for_output = port

        for connect_host, connect_port in connection_candidates:
            try:
                raw_status, latency = await _fetch_raw_status_payload(
                    connect_host=connect_host,
                    connect_port=connect_port,
                    handshake_host=hostname,
                    handshake_port=port,
                )
                resolved_host_for_output = connect_host
                resolved_port_for_output = connect_port
                break
            except Exception as connect_error:
                attempt_errors.append(
                    f"{connect_host}:{connect_port} -> {type(connect_error).__name__}: {connect_error}"
                )

        if raw_status is None or latency is None:
            if attempt_errors:
                raise RuntimeError("; ".join(attempt_errors))
            raise RuntimeError("状态查询失败")

        players = raw_status.get("players", {}) if isinstance(raw_status.get("players"), dict) else {}
        version = raw_status.get("version", {})
        raw_description = raw_status.get("description")

        response_data: dict[str, Any] = {
            **fallback_response,
            "online": True,
            "hostname": resolved_host_for_output,
            "port": resolved_port_for_output,
            "ping": latency,
            "version": version.get("name", "N/A") if isinstance(version, dict) else str(version),
            "protocol": version.get("protocol") if isinstance(version, dict) else None,
            "players": {
                "online": players.get("online", 0),
                "max": players.get("max", 0),
                "sample": _normalize_player_sample(players.get("sample")),
            },
        }

        if raw_description is not None:
            response_data["description_raw"] = raw_description
            normalized_description = _normalize_description(raw_description)
            if normalized_description:
                response_data["description"] = normalized_description

        favicon = raw_status.get("favicon")
        if favicon:
            response_data["favicon"] = favicon

        return response_data
    except Exception as exc:
        fallback_response["error"] = str(exc)
        return fallback_response


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "timeout": STATUS_QUERY_TIMEOUT,
    }


@app.get("/status")
async def status(query: str = Query(..., min_length=1, description="服务器地址，例如 mc.example.com:25565")) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    return await get_single_server_status(query)
