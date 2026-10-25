from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from PIL import Image

from xducraft_keyword import data_manager as dm
from xducraft_keyword import reply_codec as codec


def _png_bytes(color: tuple[int, int, int, int] = (20, 40, 60, 255)) -> bytes:
    output = BytesIO()
    Image.new("RGBA", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


def _media_dir(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "media"
    monkeypatch.setattr(dm, "MEDIA_DIR", str(path))
    return path


def test_uploaded_image_uses_content_hash_and_reports_actual_mime(monkeypatch, tmp_path):
    media_dir = _media_dir(monkeypatch, tmp_path)
    content = _png_bytes()

    name = codec.store_uploaded_image(content)

    assert name == hashlib.sha256(content).hexdigest()[:32] + ".img"
    path = media_dir / name
    assert path.read_bytes() == content
    assert codec.media_path_checked(name) == path.resolve()
    assert codec.image_mime(path) == "image/png"
    assert codec.store_uploaded_image(content) == name
    assert not list(media_dir.glob("*.tmp"))


@pytest.mark.parametrize(
    ("image_format", "mode", "mime"),
    [
        ("PNG", "RGBA", "image/png"),
        ("JPEG", "RGB", "image/jpeg"),
        ("GIF", "RGBA", "image/gif"),
        ("WEBP", "RGBA", "image/webp"),
    ],
)
def test_allowed_image_formats_are_detected_from_content(
    monkeypatch,
    tmp_path,
    image_format,
    mode,
    mime,
):
    _media_dir(monkeypatch, tmp_path)
    output = BytesIO()
    Image.new(mode, (2, 2)).save(output, format=image_format)

    name = codec.store_uploaded_image(output.getvalue())

    assert codec.image_mime(codec.media_path_checked(name)) == mime


def test_decompression_bomb_protection_is_not_suppressed(monkeypatch, tmp_path):
    _media_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(ValueError, match="^invalid_image$"):
        codec.store_uploaded_image(_png_bytes())


@pytest.mark.parametrize("content", [b"", b"<svg></svg>", b"not an image"])
def test_uploaded_image_rejects_non_images_without_writing(monkeypatch, tmp_path, content):
    media_dir = _media_dir(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="^invalid_image$"):
        codec.store_uploaded_image(content)

    assert not media_dir.exists()


def test_uploaded_image_rejects_oversize_content(monkeypatch, tmp_path):
    media_dir = _media_dir(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="^image_too_large$"):
        codec.store_uploaded_image(b"x" * (codec.MAX_MEDIA_BYTES + 1))

    assert not media_dir.exists()


@pytest.mark.parametrize(
    "name",
    ["../secret.img", "A" * 32 + ".img", "a" * 31 + ".img", "a" * 32 + ".png"],
)
def test_media_path_rejects_names_outside_opaque_hash_namespace(monkeypatch, tmp_path, name):
    _media_dir(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="^invalid_media_name$"):
        codec.media_path_checked(name)


def test_visual_segments_round_trip_and_escape_text_cq(monkeypatch, tmp_path):
    _media_dir(monkeypatch, tmp_path)
    name = codec.store_uploaded_image(_png_bytes())
    visual = [[
        {"type": "text", "text": "literal [CQ:at,qq=all] & tail"},
        {"type": "image", "name": name},
        {"type": "face", "id": "14"},
        {"type": "at", "qq": "all"},
        {"type": "at", "qq": "123456"},
    ]]

    persisted = codec.segments_to_replies(visual, [])
    parsed = Message(persisted[0])

    assert [segment.type for segment in parsed] == ["text", "image", "face", "at", "at"]
    assert parsed[0].data["text"] == "literal [CQ:at,qq=all] & tail"
    assert parsed[1].data == {"file": f"kwlocal://{name}"}
    assert parsed[2].data == {"id": "14"}
    assert parsed[3].data == {"qq": "all"}
    assert parsed[4].data == {"qq": "123456"}
    assert codec.replies_to_segments(persisted) == visual


def test_missing_and_noneditable_segments_are_opaque(monkeypatch, tmp_path):
    _media_dir(monkeypatch, tmp_path)
    missing = "a" * 32 + ".img"
    old = [
        "before"
        "[CQ:record,file=https://example.test/audio.amr]"
        f"[CQ:image,file=kwlocal://{missing}]"
        "after"
    ]

    visual = codec.replies_to_segments(old)

    assert visual[0][0] == {"type": "text", "text": "before"}
    assert visual[0][1]["type"] == "opaque"
    assert visual[0][1]["ref"] == {"reply_index": 0, "segment_index": 1}
    assert visual[0][2]["type"] == "opaque"
    assert visual[0][2]["ref"] == {"reply_index": 0, "segment_index": 2}
    assert visual[0][3] == {"type": "text", "text": "after"}

    moved = [[visual[0][2], {"type": "text", "text": " / "}, visual[0][1]]]
    persisted = codec.segments_to_replies(moved, old)
    expected = (
        f"[CQ:image,file=kwlocal://{missing}] / "
        "[CQ:record,file=https://example.test/audio.amr]"
    )
    assert persisted == [expected]


@pytest.mark.parametrize(
    "segment",
    [
        {"type": "opaque", "ref": {"reply_index": 0, "segment_index": 99}, "label": "x"},
        {"type": "opaque", "ref": {"reply_index": 0, "segment_index": 0}, "label": "x"},
        {"type": "opaque", "ref": {"reply_index": True, "segment_index": 1}, "label": "x"},
        {"type": "opaque", "ref": {"reply_index": 0, "segment_index": 1}, "label": "x", "raw": "forbidden"},
    ],
)
def test_opaque_references_must_target_an_old_opaque_segment(segment):
    old = ["text[CQ:video,file=https://example.test/video.mp4]"]

    with pytest.raises(ValueError):
        codec.segments_to_replies([[segment]], old)


def test_opaque_reference_cannot_be_duplicated():
    old = ["[CQ:json,data={}]"]
    opaque = codec.replies_to_segments(old)[0][0]

    with pytest.raises(ValueError, match="^invalid_opaque_reference$"):
        codec.segments_to_replies([[opaque, opaque]], old)


def test_opaque_segment_preserves_original_cq_serialization():
    old = ["[CQ:json,data=&#91;value&#93;,]"]
    opaque = codec.replies_to_segments(old)[0][0]

    assert codec.segments_to_replies([[opaque]], old) == old


@pytest.mark.parametrize(
    "segment,error",
    [
        ({"type": "text", "text": ""}, "invalid_text_segment"),
        ({"type": "text", "text": "ok", "raw": "x"}, "invalid_segment"),
        ({"type": "image", "name": "a" * 32 + ".img"}, "invalid_image_reference"),
        ({"type": "face", "id": "-1"}, "invalid_face_segment"),
        ({"type": "at", "qq": "0"}, "invalid_at_segment"),
        ({"type": "at", "qq": "someone"}, "invalid_at_segment"),
        ({"type": "record", "file": "x"}, "invalid_segment_type"),
    ],
)
def test_invalid_editor_segments_are_rejected(monkeypatch, tmp_path, segment, error):
    _media_dir(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match=f"^{error}$"):
        codec.segments_to_replies([[segment]], [])


def test_reply_count_and_serialized_length_are_bounded():
    too_many = [[{"type": "text", "text": "x"}]] * (dm.MAX_REPLIES_PER_TRIGGER + 1)
    with pytest.raises(ValueError, match="^invalid_replies$"):
        codec.segments_to_replies(too_many, [])

    # Each '[' is escaped to '&#91;', so the persisted CQ string is over 4096 chars.
    with pytest.raises(ValueError, match="^reply_too_long$"):
        codec.segments_to_replies(
            [[{"type": "text", "text": "[" * dm.MAX_REPLY_LENGTH}]],
            [],
        )

    assert codec.segments_to_replies([], []) == []


def test_restore_reply_only_resolves_existing_safe_media(monkeypatch, tmp_path):
    _media_dir(monkeypatch, tmp_path)
    name = codec.store_uploaded_image(_png_bytes())
    missing = "b" * 32 + ".img"

    restored = codec.restore_reply(
        f"one[CQ:image,file=kwlocal://{name}]"
        f"two[CQ:image,file=kwlocal://{missing}]"
        "three[CQ:image,file=kwlocal://../secret.img]"
    )

    assert f"[CQ:image,file=file:///{codec.media_path_checked(name).as_posix()}]" in restored
    assert restored.count("[图片已失效]") == 2
    assert "kwlocal://" not in restored


@pytest.mark.asyncio
async def test_persist_reply_media_keeps_qq_recording_semantics(monkeypatch, tmp_path):
    media_dir = _media_dir(monkeypatch, tmp_path)
    content = _png_bytes((100, 120, 140, 255))
    url = "https://example.test/image.png"
    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        async def respond(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == url
            return httpx.Response(200, content=content)

        return real_client(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(codec.httpx, "AsyncClient", make_client)
    message = Message([
        MessageSegment.reply(123),
        MessageSegment.text("caption"),
        MessageSegment.image(url),
    ])

    persisted = await codec.persist_reply_media(message)

    name = hashlib.sha256(url.encode()).hexdigest()[:32] + ".img"
    assert persisted == f"caption[CQ:image,file=kwlocal://{name}]"
    assert (media_dir / name).read_bytes() == content
