"""Same-origin local administration API and static UI."""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from .avatars import AvatarUnavailable, GroupAvatarCache
from .auth import AdminAuth
from .models import positive_id
from .service import AdminError, AdminService

COOKIE = "xducraft_admin_session"
CSP = "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"


def error_response(exc: AdminError):
    return JSONResponse(
        {"error": {"code": exc.code, "message": exc.message, "fields": exc.fields}},
        status_code=exc.status,
    )


async def limited_body(request: Request, maximum: int) -> bytes:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum:
            raise AdminError(413, "body_too_large", "请求内容超过限制")
        content.extend(chunk)
    return bytes(content)


async def json_body(request: Request, maximum: int = 2 * 1024 * 1024) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise AdminError(415, "content_type", "请使用 JSON 请求")
    try:
        data = json.loads(await limited_body(request, maximum))
    except (ValueError, UnicodeError):
        raise AdminError(422, "invalid_json", "JSON 内容不合法") from None
    if not isinstance(data, dict):
        raise AdminError(422, "invalid_json", "请求必须为对象")
    return data


def create_app(service: AdminService, auth: AdminAuth, static_dir: Path) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    static_dir = Path(static_dir).resolve()
    avatar_cache = GroupAvatarCache()

    @app.middleware("http")
    async def boundary(request, call_next):
        try:
            host = request.headers.get("host", "")
            parsed = urlsplit("//" + host)
            if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.username or parsed.password:
                raise AdminError(403, "invalid_host", "仅允许本地管理访问")
            try:
                parsed.port
                peer_ok = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
            except ValueError:
                peer_ok = False
            if not peer_ok:
                raise AdminError(403, "invalid_peer", "仅允许回环连接")
            write = request.method not in ("GET", "HEAD", "OPTIONS")
            if write and request.headers.get("origin") != "http://" + host:
                raise AdminError(403, "invalid_origin", "请求来源不合法")
            path = request.url.path
            if path.startswith("/api") and path != "/api/auth/login":
                token = request.cookies.get(COOKIE)
                if auth.session(token) is None:
                    raise AdminError(401, "unauthenticated", "请先登录")
                if write and not auth.verify_csrf(token, request.headers.get("x-csrf-token")):
                    raise AdminError(403, "invalid_csrf", "请求校验失败，请刷新页面")
            response = await call_next(request)
        except AdminError as exc:
            response = error_response(exc)
        except Exception:
            response = error_response(AdminError(500, "internal_error", "操作失败，配置未确认保存"))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AdminError)
    async def admin_error(_request, exc):
        return error_response(exc)

    @app.post("/api/auth/login")
    async def login(request: Request):
        body = await json_body(request, 4096)
        if set(body) != {"password"} or not isinstance(body["password"], str):
            raise AdminError(422, "invalid_login", "请输入管理口令")
        result = auth.login(body["password"])
        if result is None:
            raise AdminError(401, "invalid_password", "管理口令错误")
        token = result.pop("session_token")
        response = JSONResponse(result)
        response.set_cookie(COOKIE, token, max_age=12 * 3600, httponly=True, samesite="strict", secure=False, path="/")
        return response

    @app.get("/api/auth/session")
    async def session(request: Request):
        return auth.session(request.cookies.get(COOKIE))

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        auth.logout(request.cookies.get(COOKIE))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
        return response

    @app.get("/api/overview")
    async def overview():
        return await service.overview()

    @app.get("/api/groups")
    async def groups():
        return await service.groups()

    @app.get("/api/plugins")
    async def plugins():
        return service.plugins()

    def gid_value(gid: str) -> int:
        try:
            return positive_id(gid)
        except ValueError:
            raise AdminError(422, "invalid_group_id", "群号须为正整数") from None

    @app.get("/api/groups/{gid}/avatar")
    async def group_avatar(gid: str):
        try:
            avatar = await avatar_cache.get(gid_value(gid))
        except AvatarUnavailable:
            raise AdminError(502, "avatar_unavailable", "群头像暂时不可用") from None
        return Response(content=avatar.content, media_type=avatar.media_type)

    @app.get("/api/groups/{gid}/plugins")
    async def group_plugins(gid: str):
        return service.plugins(gid_value(gid))

    @app.get("/api/groups/{gid}/features/{key}")
    async def group_feature(gid: str, key: str):
        return service.get_feature(key, gid_value(gid))

    @app.put("/api/groups/{gid}/features/{key}")
    async def put_group_feature(gid: str, key: str, request: Request):
        return service.put_feature(key, gid_value(gid), await json_body(request), request.headers.get("if-match"))


    @app.get("/api/groups/{gid}/plugins/{plugin}/enabled")
    async def group_control(gid: str, plugin: str):
        return service.get_control(plugin, gid_value(gid))

    @app.put("/api/groups/{gid}/plugins/{plugin}/enabled")
    async def put_group_control(gid: str, plugin: str, request: Request):
        return service.put_control(plugin, gid_value(gid), await json_body(request), request.headers.get("if-match"))


    @app.get("/api/plugins/{plugin}/enabled")
    async def global_control(plugin: str):
        return service.get_control(plugin)

    @app.put("/api/plugins/{plugin}/enabled")
    async def put_global_control(plugin: str, request: Request):
        return service.put_control(plugin, None, await json_body(request), request.headers.get("if-match"))


    @app.get("/api/groups/{gid}/config/{plugin}")
    async def group_config(gid: str, plugin: str):
        return service.get_config(plugin, gid_value(gid), scope="group")

    @app.put("/api/groups/{gid}/config/{plugin}")
    async def put_group_config(gid: str, plugin: str, request: Request):
        return await service.put_config(plugin, gid_value(gid), await json_body(request), request.headers.get("if-match"), scope="group")

    @app.post("/api/groups/{gid}/config/{plugin}/apply")
    async def apply_group_config(gid: str, plugin: str, request: Request):
        return await service.recover_config(plugin, gid_value(gid), request.headers.get("if-match"), scope="group")

    @app.post("/api/groups/{gid}/config/{plugin}/rollback")
    async def rollback_group_config(gid: str, plugin: str, request: Request):
        return await service.recover_config(plugin, gid_value(gid), request.headers.get("if-match"), scope="group", rollback=True)

    @app.get("/api/global/config/{plugin}")
    async def global_config(plugin: str):
        return service.get_config(plugin, scope="global")

    @app.put("/api/global/config/{plugin}")
    async def put_global_config(plugin: str, request: Request):
        return await service.put_config(plugin, None, await json_body(request), request.headers.get("if-match"), scope="global")

    @app.post("/api/global/config/{plugin}/apply")
    async def apply_global_config(plugin: str, request: Request):
        return await service.recover_config(plugin, None, request.headers.get("if-match"), scope="global")

    @app.post("/api/global/config/{plugin}/rollback")
    async def rollback_global_config(plugin: str, request: Request):
        return await service.recover_config(plugin, None, request.headers.get("if-match"), scope="global", rollback=True)

    @app.get("/api/startup/config/{plugin}")
    async def startup_config(plugin: str):
        return service.get_config(plugin, scope="startup")

    @app.put("/api/startup/config/{plugin}")
    async def put_startup_config(plugin: str, request: Request):
        return await service.put_config(plugin, None, await json_body(request), request.headers.get("if-match"), scope="startup")

    @app.post("/api/startup/config/{plugin}/apply")
    async def apply_startup_config(plugin: str, request: Request):
        return await service.recover_config(plugin, None, request.headers.get("if-match"), scope="startup")

    @app.post("/api/startup/config/{plugin}/rollback")
    async def rollback_startup_config(plugin: str, request: Request):
        return await service.recover_config(plugin, None, request.headers.get("if-match"), scope="startup", rollback=True)

    @app.post("/api/plugins/{plugin}/media")
    async def upload_media(plugin: str, request: Request):
        provider = service.media_provider(plugin)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        allowed = {str(value).lower() for value in provider.mime_types}
        if content_type not in allowed:
            raise AdminError(415, "invalid_media", "媒体类型不受支持")
        content = await limited_body(request, int(provider.max_bytes))
        return await service.upload_media(plugin, content)

    @app.get("/api/plugins/{plugin}/media/{name}")
    async def read_media(plugin: str, name: str):
        path, mime = service.resolve_media(plugin, name)
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "no-store"})

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def unknown_api(rest: str):
        raise AdminError(404, "unknown_resource", "接口不存在")

    @app.get("/{path:path}")
    async def static(path: str):
        if not (static_dir / "index.html").is_file():
            return PlainTextResponse("网页尚未构建。请在 webui 目录执行 npm ci && npm run build。", status_code=503)
        target = (static_dir / (path or "index.html")).resolve()
        if not target.is_relative_to(static_dir) or not target.is_file():
            return PlainTextResponse("Not found", status_code=404)
        return FileResponse(target)

    return app
