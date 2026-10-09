"""Same-origin local administration API and static UI."""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, PlainTextResponse

from .avatars import AvatarUnavailable, GroupAvatarCache
from .auth import AdminAuth
from .models import positive_id
from .service import AdminError, AdminService

COOKIE = "xducraft_admin_session"
CSP = "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"


def error_response(exc):
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, "fields": exc.fields}}, status_code=exc.status)


async def limited_body(request: Request, maximum: int):
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum:
            raise AdminError(413, "body_too_large", "请求内容超过限制")
        content.extend(chunk)
    return bytes(content)


async def json_body(request: Request, maximum=2 * 1024 * 1024):
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
            if write:
                if request.headers.get("origin") != "http://" + host:
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
    async def admin_error(request, exc):
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
        return service.overview()

    @app.get("/api/groups")
    async def groups():
        return await service.groups()


    def gid_value(gid):
        try:
            return positive_id(gid)
        except ValueError:
            raise AdminError(422, "invalid_group_id", "群号须为正整数") from None

    @app.get("/api/groups/{gid}/avatar")
    async def group_avatar(gid: str):
        try:
            avatar = await avatar_cache.get(gid_value(gid))
        except AvatarUnavailable:
            raise AdminError(
                502,
                "avatar_unavailable",
                "群头像暂时不可用",
            ) from None
        return Response(content=avatar.content, media_type=avatar.media_type)

    @app.get("/api/groups/{gid}/plugins")
    async def plugins(gid: str):
        return service.plugins(gid_value(gid))

    @app.get("/api/groups/{gid}/features/{key}")
    async def group_feature(gid: str, key: str):
        return service.get_feature(key, gid_value(gid))

    @app.put("/api/groups/{gid}/features/{key}")
    async def put_group_feature(gid: str, key: str, request: Request):
        body = await json_body(request)
        return service.put_feature(key, gid_value(gid), body, request.headers.get("if-match"))

    @app.delete("/api/groups/{gid}/features/{key}")
    async def reset_group_feature(gid: str, key: str, request: Request):
        return service.put_feature(key, gid_value(gid), None, request.headers.get("if-match"), reset=True)

    @app.get("/api/global/features/{key}")
    async def global_feature(key: str):
        return service.get_feature(key)

    @app.put("/api/global/features/{key}")
    async def put_global_feature(key: str, request: Request):
        body = await json_body(request)
        return service.put_feature(key, None, body, request.headers.get("if-match"))

    @app.get("/api/groups/{gid}/config/{plugin}")
    async def group_config(gid: str, plugin: str):
        return service.get_config(plugin, gid_value(gid))

    @app.put("/api/groups/{gid}/config/{plugin}")
    async def put_group_config(gid: str, plugin: str, request: Request):
        body = await json_body(request)
        return service.put_config(plugin, gid_value(gid), body, request.headers.get("if-match"))

    @app.get("/api/global/config/{plugin}")
    async def global_config(plugin: str):
        return service.get_config(plugin)

    @app.put("/api/global/config/{plugin}")
    async def put_global_config(plugin: str, request: Request):
        body = await json_body(request)
        return service.put_config(plugin, None, body, request.headers.get("if-match"))

    @app.get("/api/groups/{gid}/invite")
    async def invite(gid: str):
        return service.get_invite(gid_value(gid))

    @app.put("/api/groups/{gid}/invite")
    async def put_invite(gid: str, request: Request):
        body = await json_body(request)
        return service.put_invite(gid_value(gid), body, request.headers.get("if-match"))

    @app.get("/api/deployment")
    async def deployment():
        return service.get_deployment()

    @app.put("/api/deployment")
    async def put_deployment(request: Request):
        body = await json_body(request)
        return service.put_deployment(body, request.headers.get("if-match"))

    @app.post("/api/keyword/media")
    async def upload(request: Request):
        service.adapter("keyword")
        if request.headers.get("content-type", "").split(";", 1)[0].lower() not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
            raise AdminError(415, "invalid_image", "仅支持 PNG、JPEG、GIF、WEBP")
        from xducraft_bot.plugins.xducraft_keyword.reply_codec import store_uploaded_image, MAX_MEDIA_BYTES
        content = await limited_body(request, MAX_MEDIA_BYTES)
        try:
            name = store_uploaded_image(content)
        except ValueError:
            raise AdminError(415, "invalid_image", "图片损坏或格式不支持") from None
        return {"name": name}

    @app.get("/api/keyword/media/{name}")
    async def media(name: str):
        service.adapter("keyword")
        from xducraft_bot.plugins.xducraft_keyword.reply_codec import media_path_checked, image_mime
        try:
            path = media_path_checked(name)
            mime = image_mime(path)
        except (ValueError, OSError):
            raise AdminError(404, "media_not_found", "图片不存在") from None
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
