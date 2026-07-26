"""OneBot 消息 ⇄ 可持久化内容树。

撤回后要能原样还原一条消息，难点有三个：

1. **图片/表情包**：消息里存的是 QQ 的临时 URL，撤回后不久就会失效。
   所以撤回时必须把文件抓下来存本地，展示时用本地路径。
2. **合并转发**：段里只有一个 ``id``，内容要另外调 ``get_forward_msg`` 取，
   而且转发里还能再套转发。原消息一撤回，这个 id 也取不到了，
   因此必须在**缓存阶段**就递归展开好。
3. **发送人**：合并转发的每个节点都带自己的昵称和 QQ 号，重建时要原样放回去，
   否则所有内容都会显示成机器人自己发的。
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Optional, Sequence

import httpx
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger

#: 转发最多展开这么多层，防御自引用或恶意构造的深层嵌套。
MAX_FORWARD_DEPTH = 5
#: 单条消息最多展开这么多个转发节点。
MAX_FORWARD_NODES = 200
#: 查询时拍平嵌套转发后的总节点上限，避免一条恶意转发膨胀成成千上万条私信。
MAX_DECODED_FORWARD_NODES = 500
DOWNLOAD_TIMEOUT = 20.0

_EXTENSION_PATTERN = re.compile(r"\.(png|jpe?g|gif|webp|bmp)\b", re.IGNORECASE)

#: 无法结构化保存、只能留个说明的段类型。
_SUMMARY_LABELS = {
    "record": "[语音]",
    "video": "[视频]",
    "file": "[文件]",
    "share": "[分享链接]",
    "json": "[卡片消息]",
    "xml": "[XML 消息]",
    "music": "[音乐分享]",
    "location": "[位置]",
    "poke": "[戳一戳]",
    "dice": "[骰子]",
    "rps": "[猜拳]",
}


def _segment_data(segment: MessageSegment) -> Dict[str, Any]:
    data = getattr(segment, "data", {}) or {}
    return dict(data) if isinstance(data, dict) else {}


async def encode_message(
    message: Message,
    bot: Optional[Bot] = None,
    depth: int = 0,
) -> List[Dict[str, Any]]:
    """把一条 OneBot 消息转成可以 JSON 序列化的内容树。

    ``bot`` 非空时会递归展开合并转发。
    """
    encoded: List[Dict[str, Any]] = []

    for segment in message:
        segment_type = getattr(segment, "type", "")
        data = _segment_data(segment)

        if segment_type == "text":
            text = str(data.get("text", ""))
            if text:
                encoded.append({"type": "text", "text": text})

        elif segment_type == "image":
            # 表情包和普通图片都是 image 段，靠 sub_type 区分（1 = 表情）。
            encoded.append({
                "type": "image",
                "url": str(data.get("url") or data.get("file") or ""),
                "file": "",
                "summary": "[动画表情]" if str(data.get("sub_type", "")) == "1" else "[图片]",
            })

        elif segment_type == "face":
            encoded.append({"type": "face", "id": str(data.get("id", ""))})

        elif segment_type == "at":
            encoded.append({
                "type": "at",
                "qq": str(data.get("qq", "")),
                "name": str(data.get("name", "") or ""),
            })

        elif segment_type == "reply":
            encoded.append({"type": "reply", "id": str(data.get("id", ""))})

        elif segment_type == "forward":
            nodes = await _expand_forward(bot, str(data.get("id", "")), depth)
            encoded.append({"type": "forward", "nodes": nodes})

        elif segment_type == "node":
            # 消息里直接内联的节点（少见，但 go-cqhttp 系会出现）。
            node = await _encode_node(data, bot, depth)
            if node:
                encoded.append({"type": "forward", "nodes": [node]})

        else:
            encoded.append({
                "type": "other",
                "raw": str(segment),
                "summary": _SUMMARY_LABELS.get(segment_type, f"[{segment_type}]"),
            })

    return encoded


async def _encode_node(data: Dict[str, Any], bot: Optional[Bot], depth: int) -> Optional[Dict[str, Any]]:
    """把一个合并转发节点转成内容树节点，保留发送人。"""
    sender = data.get("sender") if isinstance(data.get("sender"), dict) else {}
    name = (
        data.get("name")
        or data.get("nickname")
        or sender.get("card")
        or sender.get("nickname")
        or "未知用户"
    )
    uin = data.get("uin") or data.get("user_id") or sender.get("user_id") or 0

    raw_content = data.get("content", data.get("message", []))
    if isinstance(raw_content, (str, list)):
        try:
            inner = Message(raw_content)
        except Exception:
            inner = Message(str(raw_content))
    elif isinstance(raw_content, Message):
        inner = raw_content
    else:
        inner = Message(str(raw_content))

    return {
        "name": str(name),
        "uin": str(uin),
        "time": int(data.get("time", 0) or 0),
        "content": await encode_message(inner, bot, depth + 1),
    }


async def _expand_forward(bot: Optional[Bot], forward_id: str, depth: int) -> List[Dict[str, Any]]:
    """调 ``get_forward_msg`` 展开合并转发，并递归处理嵌套转发。"""
    if bot is None or not forward_id or depth >= MAX_FORWARD_DEPTH:
        return []

    payload = None
    last_error: Optional[Exception] = None
    # OneBot v11 标准字段是 id；部分实现（如某些 NapCat 版本）只接受
    # message_id。不能把两个未知参数一次性都塞过去，否则严格实现会直接拒绝。
    for parameter in ({"id": forward_id}, {"message_id": forward_id}):
        try:
            payload = await bot.call_api("get_forward_msg", **parameter)
            break
        except Exception as exc:
            last_error = exc

    if payload is None:
        logger.debug("[AntiRecall] 展开合并转发 {} 失败: {}", forward_id, last_error)
        return []

    raw_nodes = []
    if isinstance(payload, dict):
        raw_nodes = payload.get("messages") or payload.get("message") or []
    elif isinstance(payload, list):
        raw_nodes = payload

    nodes: List[Dict[str, Any]] = []
    for raw_node in raw_nodes[:MAX_FORWARD_NODES]:
        if not isinstance(raw_node, dict):
            continue
        # 有的实现把内容包在 data 里，有的直接摊平。
        source = raw_node.get("data") if isinstance(raw_node.get("data"), dict) else raw_node
        node = await _encode_node(source, bot, depth)
        if node:
            nodes.append(node)

    return nodes


# ==============================================================================
# 媒体下载
# ==============================================================================

def _guess_extension(url: str, content_type: str = "") -> str:
    match = _EXTENSION_PATTERN.search(url)
    if match:
        return f".{match.group(1).lower()}"
    subtype = content_type.lower().partition("/")[2].partition(";")[0].strip()
    if subtype in {"png", "gif", "webp", "bmp"}:
        return f".{subtype}"
    if subtype in {"jpeg", "jpg"}:
        return ".jpg"
    return ".dat"


async def download_media(content: Sequence[Dict[str, Any]], store, max_bytes: int) -> bool:
    """把内容树里所有图片下载到本地并回填 ``file`` 字段。

    返回是否有任何一张下载成功。失败的条目保留原 URL，展示时再碰运气。
    """
    targets: List[Dict[str, Any]] = []

    def collect(items: Any) -> None:
        if isinstance(items, list):
            for item in items:
                collect(item)
        elif isinstance(items, dict):
            if items.get("type") == "image" and items.get("url") and not items.get("file"):
                targets.append(items)
            for key in ("nodes", "content"):
                if key in items:
                    collect(items[key])

    collect(list(content))
    if not targets:
        return False

    downloaded = 0

    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async def fetch(entry: Dict[str, Any]) -> None:
            nonlocal downloaded
            url = entry["url"]
            try:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            logger.debug("[AntiRecall] 媒体超过大小上限，跳过: {}", url[:120])
                            return
                    content_type = response.headers.get("content-type", "")

                if not chunks:
                    return

                path = store.media_path(url, _guess_extension(url, content_type))
                with open(path, "wb") as handle:
                    handle.write(bytes(chunks))
                entry["file"] = os.path.basename(path)
                downloaded += 1
            except Exception as exc:
                logger.debug("[AntiRecall] 下载媒体失败 {}: {}", url[:120], exc)

        await asyncio.gather(*(fetch(entry) for entry in targets), return_exceptions=True)

    return downloaded > 0


# ==============================================================================
# 还原
# ==============================================================================

def decode_message(content: Sequence[Dict[str, Any]], media_dir: str) -> Message:
    """把内容树还原成一条可发送的 OneBot 消息。"""
    message = Message()

    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "text":
            message += MessageSegment.text(str(item.get("text", "")))

        elif item_type == "image":
            file_name = str(item.get("file") or "")
            if file_name:
                local_path = os.path.join(media_dir, os.path.basename(file_name))
                if os.path.exists(local_path):
                    message += MessageSegment.image(file=f"file:///{local_path}")
                    continue
            url = str(item.get("url") or "")
            if url:
                # 本地文件没了就退回原 URL，多半已失效，但总比什么都不显示强。
                message += MessageSegment.image(file=url)
            else:
                message += MessageSegment.text(str(item.get("summary", "[图片]")))

        elif item_type == "face":
            face_id = str(item.get("id", ""))
            if face_id.isdigit():
                message += MessageSegment.face(int(face_id))

        elif item_type == "at":
            name = item.get("name") or item.get("qq")
            # 还原时不真的 @ 人：查看撤回记录不该把人再叫一遍。
            message += MessageSegment.text(f"@{name} ")

        elif item_type == "reply":
            message += MessageSegment.text("[回复] ")

        elif item_type == "forward":
            nodes = item.get("nodes") or []
            message += MessageSegment.text(f"[合并转发 · {len(nodes)} 条]")

        else:
            message += MessageSegment.text(str(item.get("summary", "[未知消息]")))

    if not message:
        message += MessageSegment.text("[空消息]")
    return message


def decode_forward_nodes(content: Sequence[Dict[str, Any]], media_dir: str, self_id: int) -> List[Dict[str, Any]]:
    """把内容树里的合并转发还原成可再次发送的节点列表。

    嵌套转发会被拍平成带缩进前缀的节点——QQ 不支持无限层级的转发嵌套，
    但拍平后**每个节点仍然保留自己的原始发送人**，不会丢失“谁说的”。
    """
    nodes: List[Dict[str, Any]] = []

    def walk(items: Sequence[Dict[str, Any]], depth: int) -> None:
        for item in items:
            if len(nodes) >= MAX_DECODED_FORWARD_NODES:
                return
            if not isinstance(item, dict) or item.get("type") != "forward":
                continue
            for node in item.get("nodes") or []:
                if len(nodes) >= MAX_DECODED_FORWARD_NODES:
                    return
                if not isinstance(node, dict):
                    continue
                prefix = "　" * depth + ("└ " if depth else "")
                inner = node.get("content") or []
                body = decode_message(inner, media_dir)
                if prefix:
                    body = MessageSegment.text(prefix) + body
                nodes.append({
                    "type": "node",
                    "data": {
                        "name": str(node.get("name", "未知用户")),
                        "uin": str(node.get("uin") or self_id),
                        "content": body,
                    },
                })
                walk(inner, depth + 1)

    walk(list(content), 0)
    return nodes


def summarize_content(content: Sequence[Dict[str, Any]], limit: int = 60) -> str:
    """一行摘要，用于列表展示。"""
    parts: List[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            parts.append(str(item.get("text", "")).replace("\n", " "))
        elif item_type == "image":
            parts.append(str(item.get("summary", "[图片]")))
        elif item_type == "face":
            parts.append("[表情]")
        elif item_type == "at":
            parts.append(f"@{item.get('name') or item.get('qq')}")
        elif item_type == "forward":
            parts.append(f"[合并转发 {len(item.get('nodes') or [])} 条]")
        elif item_type == "reply":
            continue
        else:
            parts.append(str(item.get("summary", "[消息]")))

    text = "".join(parts).strip() or "[空消息]"
    return text[:limit] + ("…" if len(text) > limit else "")


__all__ = [
    "encode_message", "decode_message", "decode_forward_nodes",
    "download_media", "summarize_content", "MAX_FORWARD_DEPTH",
    "MAX_DECODED_FORWARD_NODES",
]
