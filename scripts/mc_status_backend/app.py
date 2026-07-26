"""XDUCraft MC 状态查询后端。

独立部署在**能连上服务器的那台机器**上，供机器人以 ``custom`` 数据源调用。
典型场景：机器人跑在校外，Minecraft 服务器只在校内网可达。

启动::

    uvicorn app:app --host 0.0.0.0 --port 8000

协议实现与机器人共用 ``xducraft_bot.shared.mc_protocol``，不再各留一份拷贝。
单文件部署（只拷这个 app.py 出去）时会自动回退到 ``mcstatus``。
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from mcstatus import JavaServer

# 允许直接从仓库里跑（app.py 在 scripts/mc_status_backend/ 下，往上两级是仓库根）。
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from xducraft_bot.shared import mc_protocol  # type: ignore  # noqa: E402
except ModuleNotFoundError:
    # 兼容旧部署方式：只把 app.py 单独复制到服务器上时没有 xducraft_bot 包，
    # 仍可通过 mcstatus 返回同一套字段（仓库内运行则始终走共享原始协议实现）。
    mc_protocol = None

STATUS_QUERY_TIMEOUT = float(os.getenv("MC_STATUS_BACKEND_TIMEOUT", "3.0"))
MAX_QUERY_LENGTH = 256

app = FastAPI(title="XDUCraft MC Status Backend", version="2.0.0")


async def _query_with_mcstatus(target: str) -> Dict[str, Any]:
    """单文件部署时的兼容查询实现。"""
    parsed = urlparse(f"//{target}")
    hostname = parsed.hostname or target
    try:
        port = parsed.port or 25565
    except ValueError:
        port = 25565

    result: Dict[str, Any] = {
        "online": False,
        "hostname": hostname,
        "port": port,
        "original_query": target,
        "ip": target,
    }

    candidates = []
    try:
        resolved = await JavaServer.async_lookup(target, timeout=STATUS_QUERY_TIMEOUT)
        candidates.append(resolved)
    except Exception:
        pass

    if not any(server.address.host == hostname and server.address.port == port for server in candidates):
        candidates.append(JavaServer(hostname, port, timeout=STATUS_QUERY_TIMEOUT))

    errors = []
    for server in candidates:
        try:
            status_result = await server.async_status()
        except Exception as exc:
            errors.append(
                f"{server.address.host}:{server.address.port} -> {type(exc).__name__}: {exc}"
            )
            continue

        raw = status_result.raw
        players = raw.get("players") if isinstance(raw.get("players"), dict) else {}
        version = raw.get("version") if isinstance(raw.get("version"), dict) else {}
        sample = []
        for player in players.get("sample") or []:
            if not isinstance(player, dict) or not player.get("name"):
                continue
            entry = {"name": str(player["name"])}
            if player.get("id") is not None:
                entry["id"] = str(player["id"])
            sample.append(entry)

        result.update({
            "online": True,
            "hostname": server.address.host,
            "port": server.address.port,
            "ping": int(round(status_result.latency)),
            "version": version.get("name", "N/A"),
            "protocol": version.get("protocol"),
            "players": {
                "online": players.get("online", 0),
                "max": players.get("max", 0),
                "sample": sample,
            },
        })
        if raw.get("description") is not None:
            result["description_raw"] = raw["description"]
            result["description"] = {
                "html": status_result.motd.to_html(),
                "text": status_result.motd.to_plain(),
            }
        if raw.get("favicon"):
            result["favicon"] = raw["favicon"]
        if "enforcesSecureChat" in raw:
            result["enforces_secure_chat"] = bool(raw.get("enforcesSecureChat"))
        return result

    result["error"] = "; ".join(errors) if errors else "状态查询失败"
    return result


async def query_server(target: str) -> Dict[str, Any]:
    if mc_protocol is not None:
        return await mc_protocol.query_status(target, timeout=STATUS_QUERY_TIMEOUT)
    return await _query_with_mcstatus(target)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "timeout": STATUS_QUERY_TIMEOUT}


@app.get("/status")
async def status(
    query: str = Query(..., min_length=1, max_length=MAX_QUERY_LENGTH,
                       description="服务器地址，例如 mc.example.com:25565"),
) -> Dict[str, Any]:
    """查询一台服务器。返回结构与机器人内部的 ``protocol`` 数据源一致。"""
    target = query.strip()
    if not target:
        raise HTTPException(status_code=400, detail="query 不能为空")

    return await query_server(target)
