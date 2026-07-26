"""服务器图标（favicon）的解码与缓存。

favicon 有两种来源：状态协议直接返回的 ``data:image/png;base64,...``，以及
聚合 API 返回的远程 URL。两者都是**外部可控输入**，所以这里有几道限制：

- 只接受 ``data:image/`` 与 ``http(s)://``，挡掉 ``file://`` 一类的本地读取；
- 下载和解码都有体积上限，避免一个几百 MB 的“图标”把机器人内存吃光；
- 任何失败都只返回 ``None``，由调用方回退到内置图标。

缓存按 URL 的 SHA-256 命名，原子写入，60 分钟过期。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from nonebot.log import logger

CACHE_DIR = Path(__file__).resolve().parent / "image_cache"
CACHE_TTL = 60 * 60
DOWNLOAD_TIMEOUT = 5.0

#: favicon 官方规格是 64x64 PNG，正常撑死几十 KB。给 4MB 已经非常宽松。
MAX_IMAGE_BYTES = 4 * 1024 * 1024

_DATA_URI_PATTERN = re.compile(r"^data:image/[\w.+-]+;base64,(?P<data>.+)$", re.DOTALL | re.IGNORECASE)


def get_cache_path(url: str) -> Path:
    """按 URL 的 SHA-256 生成缓存文件名。"""
    return CACHE_DIR / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.cache"


def is_cache_valid(cache_path: Path) -> bool:
    try:
        return (time.time() - cache_path.stat().st_mtime) < CACHE_TTL
    except OSError:
        return False


def read_from_cache(cache_path: Path) -> Optional[BytesIO]:
    try:
        return BytesIO(cache_path.read_bytes())
    except OSError as exc:
        logger.debug("[MCStatus] 读取图标缓存失败 {}: {}", cache_path.name, exc)
        return None


def write_to_cache(cache_path: Path, data: bytes) -> bool:
    """原子写入缓存，避免读到写了一半的文件。"""
    temp_path = cache_path.with_suffix(".tmp")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(data)
        temp_path.replace(cache_path)
        return True
    except OSError as exc:
        logger.debug("[MCStatus] 写入图标缓存失败 {}: {}", cache_path.name, exc)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


async def download_image_with_cache(url: str) -> Optional[BytesIO]:
    """下载远程图标，带缓存与体积上限。"""
    cache_path = get_cache_path(url)
    if is_cache_valid(cache_path):
        cached = read_from_cache(cache_path)
        if cached is not None:
            return cached

    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if content_type and not content_type.lower().startswith("image/"):
                    logger.debug("[MCStatus] 图标 URL 返回的不是图片（{}）: {}", content_type, url)
                    return None

                # 边下边计数：只看 Content-Length 挡不住不声明长度的响应。
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_IMAGE_BYTES:
                        logger.debug("[MCStatus] 图标超过 {} 字节上限，放弃: {}", MAX_IMAGE_BYTES, url)
                        return None

        data = bytes(chunks)
        if not data:
            return None

        write_to_cache(cache_path, data)
        return BytesIO(data)
    except Exception as exc:
        logger.debug("[MCStatus] 下载图标失败 {}: {}", url, exc)
        return None


def decode_base64_data(data_uri: str) -> Optional[BytesIO]:
    """解码 ``data:image/...;base64,...``。"""
    if len(data_uri) > MAX_IMAGE_BYTES * 2:  # base64 大约膨胀 4/3
        logger.debug("[MCStatus] data URI 过长，放弃解码。")
        return None

    match = _DATA_URI_PATTERN.match(data_uri.strip())
    if not match:
        return None

    payload = match.group("data").strip()
    if not payload:
        return None

    try:
        # 部分服务器会在 base64 里塞换行，validate=False 会忽略非字母表字符。
        decoded = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        logger.debug("[MCStatus] favicon base64 解码失败: {}", exc)
        return None

    if not decoded or len(decoded) > MAX_IMAGE_BYTES:
        return None
    return BytesIO(decoded)


async def decode_image(src: str) -> Optional[BytesIO]:
    """把 favicon 字段解成图片字节流；无法处理时返回 ``None``。"""
    source = str(src or "").strip()
    if not source:
        return None

    if source.lower().startswith("data:image/"):
        return decode_base64_data(source)

    scheme = urlparse(source).scheme.lower()
    if scheme not in ("http", "https"):
        logger.debug("[MCStatus] 不支持的图标地址协议: {}", scheme or "(空)")
        return None

    return await download_image_with_cache(source)


def cleanup_expired_cache() -> int:
    """清理过期缓存，返回删除数量。

    以前这个函数在模块导入时就会执行——插件加载阶段做一次同步遍历磁盘的 IO，
    缓存文件多的时候会明显拖慢启动。现在改为由调用方按需触发。
    """
    if not CACHE_DIR.exists():
        return 0

    now = time.time()
    removed = 0
    for cache_file in CACHE_DIR.glob("*.cache"):
        try:
            if now - cache_file.stat().st_mtime > CACHE_TTL:
                cache_file.unlink()
                removed += 1
        except OSError:
            continue

    if removed:
        logger.debug("[MCStatus] 清理了 {} 个过期图标缓存。", removed)
    return removed


def get_cache_stats() -> dict:
    """缓存统计，供 ``/mcs diag`` 展示。"""
    if not CACHE_DIR.exists():
        return {"total_files": 0, "valid_files": 0, "total_size": 0, "total_size_mb": 0.0}

    files = list(CACHE_DIR.glob("*.cache"))
    total_size = 0
    valid = 0
    for path in files:
        try:
            total_size += path.stat().st_size
        except OSError:
            continue
        if is_cache_valid(path):
            valid += 1

    return {
        "total_files": len(files),
        "valid_files": valid,
        "total_size": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }


__all__ = [
    "decode_image", "decode_base64_data", "download_image_with_cache",
    "cleanup_expired_cache", "get_cache_stats", "CACHE_DIR", "CACHE_TTL", "MAX_IMAGE_BYTES",
]
