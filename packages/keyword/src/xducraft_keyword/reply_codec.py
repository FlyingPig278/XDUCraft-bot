"""CQ reply conversion and persistent media handling for keyword replies."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import tempfile
import warnings
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

import httpx
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.log import logger
from PIL import Image

from . import data_manager as dm

MEDIA_DOWNLOAD_TIMEOUT = 20.0
MAX_MEDIA_BYTES = 10 * 1024 * 1024

_MEDIA_NAME_RE = re.compile(r"[a-f0-9]{32}\.img\Z")
_FACE_ID_RE = re.compile(r"[0-9]+\Z")
_QQ_ID_RE = re.compile(r"[1-9][0-9]*\Z")
_CQ_CODE_RE = re.compile(
    r"\[CQ:(?P<type>[a-zA-Z0-9-_.]+)"
    r"(?P<params>(?:,[a-zA-Z0-9-_.]+=[^,\]]*)*),?\]"
)
_ALLOWED_IMAGE_MIMES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}
_OPAQUE_LABELS = {
    "image": "不可编辑的图片",
    "record": "语音消息",
    "video": "视频消息",
    "forward": "转发消息",
    "json": "卡片消息",
    "xml": "卡片消息",
}


def media_path_checked(name: str) -> Path:
    """Return a media path only when its opaque basename stays in ``MEDIA_DIR``."""
    if not isinstance(name, str) or _MEDIA_NAME_RE.fullmatch(name) is None:
        raise ValueError("invalid_media_name")

    try:
        root = Path(dm.MEDIA_DIR).resolve()
        path = (root / name).resolve()
        path.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("unsafe_media_path") from exc
    return path


def _image_mime_from_source(source: Union[BinaryIO, Path]) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                image_format = image.format
                image.verify()
    except Exception as exc:
        raise ValueError("invalid_image") from exc

    mime = _ALLOWED_IMAGE_MIMES.get(str(image_format).upper())
    if mime is None:
        raise ValueError("unsupported_image")
    return mime


def image_mime(path: Path) -> str:
    """Verify an image with Pillow and return its allow-listed MIME type."""
    if not isinstance(path, Path):
        raise ValueError("invalid_image")
    return _image_mime_from_source(path)


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def store_uploaded_image(content: bytes) -> str:
    """Validate and atomically store an uploaded image under its content hash."""
    if not isinstance(content, bytes):
        raise ValueError("invalid_image")
    if not content:
        raise ValueError("invalid_image")
    if len(content) > MAX_MEDIA_BYTES:
        raise ValueError("image_too_large")

    _image_mime_from_source(io.BytesIO(content))
    name = hashlib.sha256(content).hexdigest()[:32] + ".img"
    _write_atomic(media_path_checked(name), content)
    return name


def restore_reply(reply: str) -> str:
    """Restore persistent ``kwlocal://`` image references for OneBot sending."""
    def replace(match: re.Match[str]) -> str:
        try:
            path = media_path_checked(match.group(1))
        except ValueError:
            return "[图片已失效]"
        if not path.is_file():
            return "[图片已失效]"
        return f"[CQ:image,file=file:///{path.as_posix()}]"

    return re.sub(r"\[CQ:image,file=kwlocal://([^\]]+)\]", replace, reply)


async def persist_reply_media(message: Message) -> str:
    """Serialize a reply, downloading temporary remote images for later replay."""
    parts: list[str] = []
    downloads: list[tuple[int, str]] = []

    for segment in message:
        if segment.type == "reply":
            # A quoted message is useful while recording, but cannot be replayed later.
            continue
        if segment.type == "image":
            url = str(segment.data.get("url") or segment.data.get("file") or "")
            if url.startswith(("http://", "https://")):
                downloads.append((len(parts), url))
                parts.append("")
                continue
        parts.append(str(segment))

    if downloads:
        async with httpx.AsyncClient(
            timeout=MEDIA_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
        ) as client:
            async def fetch(index: int, url: str) -> None:
                try:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > MAX_MEDIA_BYTES:
                                parts[index] = "[图片过大未保存]"
                                return
                    name = hashlib.sha256(url.encode()).hexdigest()[:32] + ".img"
                    _write_atomic(media_path_checked(name), bytes(chunks))
                    parts[index] = f"[CQ:image,file=kwlocal://{name}]"
                except Exception as exc:
                    logger.debug("[Keyword] 下载回复图片失败: {}", type(exc).__name__)
                    parts[index] = "[图片保存失败]"

            await asyncio.gather(
                *(fetch(index, url) for index, url in downloads),
                return_exceptions=True,
            )

    return "".join(parts)


def _is_editable_image(segment: MessageSegment) -> Optional[str]:
    if segment.type != "image" or set(segment.data) != {"file"}:
        return None
    file_value = segment.data.get("file")
    if not isinstance(file_value, str) or not file_value.startswith("kwlocal://"):
        return None
    name = file_value.removeprefix("kwlocal://")
    try:
        path = media_path_checked(name)
        if not path.is_file():
            return None
        image_mime(path)
    except ValueError:
        return None
    return name


def _segment_is_opaque(segment: MessageSegment) -> bool:
    if segment.type == "text":
        return False
    if segment.type == "image":
        return _is_editable_image(segment) is None
    if segment.type == "face":
        face_id = segment.data.get("id")
        return (
            set(segment.data) != {"id"}
            or not isinstance(face_id, str)
            or _FACE_ID_RE.fullmatch(face_id) is None
        )
    if segment.type == "at":
        qq = segment.data.get("qq")
        return (
            set(segment.data) != {"qq"}
            or not isinstance(qq, str)
            or (qq != "all" and _QQ_ID_RE.fullmatch(qq) is None)
        )
    return True


def _opaque_label(segment: MessageSegment) -> str:
    return _OPAQUE_LABELS.get(segment.type, f"{segment.type} 消息")


def _raw_reply_segments(reply: str) -> list[str]:
    """Split CQ text on the same boundaries as OneBot without normalizing it."""
    parts: list[str] = []
    text_begin = 0
    for match in _CQ_CODE_RE.finditer(reply):
        if match.start() > text_begin:
            parts.append(reply[text_begin:match.start()])
        parts.append(match.group(0))
        text_begin = match.end()
    if text_begin < len(reply):
        parts.append(reply[text_begin:])
    return parts


def replies_to_segments(replies: list[str]) -> list[list[dict]]:
    """Convert persisted CQ replies into the safe visual-editor representation."""
    if not isinstance(replies, list) or len(replies) > dm.MAX_REPLIES_PER_TRIGGER:
        raise ValueError("invalid_replies")

    converted: list[list[dict]] = []
    for reply_index, reply in enumerate(replies):
        if (
            not isinstance(reply, str)
            or not reply
            or len(reply) > dm.MAX_REPLY_LENGTH
        ):
            raise ValueError("invalid_reply")
        output: list[dict] = []
        for segment_index, segment in enumerate(Message(reply)):
            if segment.type == "text":
                output.append({"type": "text", "text": str(segment.data.get("text", ""))})
                continue
            image_name = _is_editable_image(segment)
            if image_name is not None:
                output.append({"type": "image", "name": image_name})
                continue
            if segment.type == "face" and not _segment_is_opaque(segment):
                output.append({"type": "face", "id": str(segment.data["id"])})
                continue
            if segment.type == "at" and not _segment_is_opaque(segment):
                output.append({"type": "at", "qq": str(segment.data["qq"])})
                continue
            output.append({
                "type": "opaque",
                "ref": {
                    "reply_index": reply_index,
                    "segment_index": segment_index,
                },
                "label": _opaque_label(segment),
            })
        if not output:
            raise ValueError("invalid_reply")
        converted.append(output)
    return converted


def _require_exact_keys(value: dict, keys: set[str]) -> None:
    if set(value) != keys:
        raise ValueError("invalid_segment")


def _old_opaque_segment(
    old_messages: list[Message],
    old_raw_segments: list[list[str]],
    ref: Any,
) -> tuple[tuple[int, int], str]:
    if not isinstance(ref, dict) or set(ref) != {"reply_index", "segment_index"}:
        raise ValueError("invalid_opaque_reference")
    reply_index = ref.get("reply_index")
    segment_index = ref.get("segment_index")
    if (
        isinstance(reply_index, bool)
        or not isinstance(reply_index, int)
        or reply_index < 0
        or isinstance(segment_index, bool)
        or not isinstance(segment_index, int)
        or segment_index < 0
    ):
        raise ValueError("invalid_opaque_reference")
    try:
        segment = old_messages[reply_index][segment_index]
        raw_segment = old_raw_segments[reply_index][segment_index]
    except IndexError as exc:
        raise ValueError("invalid_opaque_reference") from exc
    if not _segment_is_opaque(segment):
        raise ValueError("invalid_opaque_reference")
    return (reply_index, segment_index), raw_segment


def segments_to_replies(
    replies: list[list[dict]],
    old_replies: list[str],
) -> list[str]:
    """Convert visual-editor segments to CQ, preserving referenced opaque segments."""
    if not isinstance(replies, list) or len(replies) > dm.MAX_REPLIES_PER_TRIGGER:
        raise ValueError("invalid_replies")
    if not isinstance(old_replies, list) or any(
        not isinstance(item, str) for item in old_replies
    ):
        raise ValueError("invalid_old_replies")

    old_messages = [Message(reply) for reply in old_replies]
    old_raw_segments = [_raw_reply_segments(reply) for reply in old_replies]
    used_opaque_refs: set[tuple[int, int]] = set()
    converted: list[str] = []

    for reply in replies:
        if not isinstance(reply, list) or not reply:
            raise ValueError("invalid_reply")
        parts: list[str] = []
        for item in reply:
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise ValueError("invalid_segment")
            item_type = item["type"]
            if item_type == "text":
                _require_exact_keys(item, {"type", "text"})
                text = item.get("text")
                if not isinstance(text, str) or not text:
                    raise ValueError("invalid_text_segment")
                parts.append(str(MessageSegment.text(text)))
            elif item_type == "image":
                _require_exact_keys(item, {"type", "name"})
                name = item.get("name")
                if not isinstance(name, str):
                    raise ValueError("invalid_image_reference")
                try:
                    path = media_path_checked(name)
                    if not path.is_file():
                        raise ValueError("invalid_image_reference")
                    image_mime(path)
                except ValueError as exc:
                    raise ValueError("invalid_image_reference") from exc
                image_segment = MessageSegment(
                    "image",
                    {"file": f"kwlocal://{name}"},
                )
                parts.append(str(image_segment))
            elif item_type == "face":
                _require_exact_keys(item, {"type", "id"})
                face_id = item.get("id")
                if (
                    not isinstance(face_id, str)
                    or _FACE_ID_RE.fullmatch(face_id) is None
                ):
                    raise ValueError("invalid_face_segment")
                parts.append(str(MessageSegment("face", {"id": face_id})))
            elif item_type == "at":
                _require_exact_keys(item, {"type", "qq"})
                qq = item.get("qq")
                if (
                    not isinstance(qq, str)
                    or (qq != "all" and _QQ_ID_RE.fullmatch(qq) is None)
                ):
                    raise ValueError("invalid_at_segment")
                parts.append(str(MessageSegment.at(qq)))
            elif item_type == "opaque":
                _require_exact_keys(item, {"type", "ref", "label"})
                if not isinstance(item.get("label"), str):
                    raise ValueError("invalid_opaque_reference")
                ref, old_segment = _old_opaque_segment(
                    old_messages,
                    old_raw_segments,
                    item.get("ref"),
                )
                if ref in used_opaque_refs:
                    raise ValueError("invalid_opaque_reference")
                used_opaque_refs.add(ref)
                parts.append(old_segment)
            else:
                raise ValueError("invalid_segment_type")

        persisted = "".join(parts)
        if not persisted:
            raise ValueError("invalid_reply")
        if len(persisted) > dm.MAX_REPLY_LENGTH:
            raise ValueError("reply_too_long")
        converted.append(persisted)

    return converted


class MediaProvider:
    """本插件的本地图片能力，供通用资产接口调用，不暴露目录。"""

    max_bytes = MAX_MEDIA_BYTES
    mime_types = tuple(_ALLOWED_IMAGE_MIMES.values())

    @staticmethod
    def upload(content: bytes) -> str:
        return store_uploaded_image(content)

    @staticmethod
    def resolve(name: str) -> tuple[Path, str]:
        path = media_path_checked(name)
        if not path.is_file():
            raise FileNotFoundError("media_not_found")
        return path, image_mime(path)


__all__ = [
    "MAX_MEDIA_BYTES",
    "MediaProvider",
    "MEDIA_DOWNLOAD_TIMEOUT",
    "image_mime",
    "media_path_checked",
    "persist_reply_media",
    "replies_to_segments",
    "restore_reply",
    "segments_to_replies",
    "store_uploaded_image",
]
