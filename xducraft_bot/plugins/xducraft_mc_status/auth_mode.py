"""服务器登录验证方式：数据模型 + 自动探测。

要回答的问题是：这个服务器上的人，究竟是**离线验证**进来的、走 **XDU / MUA
皮肤站**进来的，还是**正版**进来的。

状态协议本身不会告诉你这件事，但玩家样本（``players.sample``）里的 UUID 会：

1. **离线验证的 UUID 是可以精确重算的。**
   Java 版对离线玩家用 ``UUID.nameUUIDFromBytes("OfflinePlayer:<名字>")``，
   也就是 MD5 摘要 + 版本位置 3 + IETF 变体位。给定名字就能算出唯一答案，
   算出来一样就是离线，不存在误判，而且**完全不需要联网**。
2. **正版 / 外置登录要靠名字反查 UUID 再比对。**
   同一个名字可能在 Mojang 和某个皮肤站上**同时**存在，所以判定依据必须是
   “查出来的 UUID 和服务器报的 UUID 相等”，而不是“这个名字查得到”。
3. 剩下的既不是离线、也对不上 XDU、MUA 和 Mojang，那才是**别的外置登录皮肤站**。

因为样本经常是空的（0 人在线、或者服务器关掉了样本），探测天然是**尽力而为**
的，所以真正的事实来源永远是管理员配置的 ``auth_mode``，探测只用来补充和佐证。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid as uuid_module
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from nonebot.log import logger

# ==============================================================================
# 1. 模式定义
# ==============================================================================

MODE_OFFICIAL = "official"
MODE_XDU = "xdu"
MODE_MUA = "mua"
MODE_YGGDRASIL = "yggdrasil"
MODE_OFFLINE = "offline"
MODE_MIXED = "mixed"
MODE_UNKNOWN = "unknown"

#: 管理员可以显式配置的取值（``""`` 只为兼容旧配置保留）。
#: 管理界面与图例中的固定顺序，Web 编辑器和帮助文本也保持一致。
CONFIGURABLE_MODES = (MODE_OFFICIAL, MODE_MUA, MODE_XDU, MODE_YGGDRASIL, MODE_OFFLINE, MODE_MIXED)

#: 判定来源，决定展示时说“已确认”还是“据配置”。
ORIGIN_DETECTED = "detected"    # 本次查询从玩家样本里实测出来的
ORIGIN_CONFIGURED = "configured"  # 管理员配置的
ORIGIN_INHERITED = "inherited"    # 继承自群默认值
ORIGIN_NONE = "none"


@dataclass(frozen=True)
class AuthModeStyle:
    """一种验证方式的展示信息。"""

    key: str
    label: str        # 完整中文名，用于文字回复
    short_label: str  # 图片徽章上的短名（<= 4 字，避免撑爆一行）
    color: Tuple[int, int, int, int]      # 徽章底色
    text_color: Tuple[int, int, int, int]  # 徽章文字色
    description: str


_WHITE = (255, 255, 255, 255)
_INK = (24, 18, 12, 255)

AUTH_MODE_STYLES: Dict[str, AuthModeStyle] = {
    MODE_XDU: AuthModeStyle(
        key=MODE_XDU,
        label="XDU 皮肤站登录",
        short_label="XDU",
        color=(31, 111, 235, 255),
        text_color=_WHITE,
        description="玩家通过 XDUCraft 本校皮肤站（外置登录）进入服务器。",
    ),
    MODE_OFFICIAL: AuthModeStyle(
        key=MODE_OFFICIAL,
        label="正版登录",
        short_label="正版",
        color=(46, 160, 67, 255),
        text_color=_WHITE,
        description="玩家使用 Mojang / 微软正版账号进入服务器。",
    ),
    MODE_MUA: AuthModeStyle(
        key=MODE_MUA,
        label="MUA 联合登录（含 XDU）",
        short_label="MUA",
        color=(88, 101, 242, 255),
        text_color=_WHITE,
        description=(
            "MUA 是包含 XDUCraft 本校皮肤站的高校联合认证；"
            "标记为 MUA 的服务器可以直接使用 XDU 账号登录。"
        ),
    ),
    MODE_YGGDRASIL: AuthModeStyle(
        key=MODE_YGGDRASIL,
        label="第三方外置登录",
        short_label="外置",
        color=(0, 168, 181, 255),
        text_color=_WHITE,
        description="玩家通过 XDU / MUA 以外的 Yggdrasil 皮肤站进入服务器。",
    ),
    MODE_OFFLINE: AuthModeStyle(
        key=MODE_OFFLINE,
        label="离线验证",
        # 不能只写“离线”——它会紧挨着 IP 显示，和“服务器离线”混淆。
        short_label="离线登录",
        color=(219, 148, 30, 255),
        text_color=_INK,
        description="服务器未开启正版验证，玩家 UUID 由名字直接推导。",
    ),
    MODE_MIXED: AuthModeStyle(
        key=MODE_MIXED,
        label="混合验证",
        short_label="混合",
        color=(163, 113, 247, 255),
        text_color=_WHITE,
        description="同一服务器上同时存在多种登录方式（通常是装了统一登录插件）。",
    ),
    MODE_UNKNOWN: AuthModeStyle(
        key=MODE_UNKNOWN,
        label="未知验证方式",
        short_label="未知",
        color=(110, 118, 129, 255),
        text_color=_WHITE,
        description="没有可用的玩家样本，也没有配置，无法判断。",
    ),
}

#: 面向用户的别名 -> 标准值，让管理员能用中文设置。
MODE_ALIASES: Dict[str, str] = {
    "xdu": MODE_XDU, "xducraft": MODE_XDU, "西电": MODE_XDU,
    "xdu皮肤站": MODE_XDU, "西电皮肤站": MODE_XDU, "本校": MODE_XDU,
    "official": MODE_OFFICIAL, "mojang": MODE_OFFICIAL, "premium": MODE_OFFICIAL,
    "online": MODE_OFFICIAL, "正版": MODE_OFFICIAL, "正版登录": MODE_OFFICIAL,
    "mua": MODE_MUA, "union": MODE_MUA, "联合": MODE_MUA, "联合登录": MODE_MUA,
    "mua联合": MODE_MUA, "联合皮肤站": MODE_MUA,
    "yggdrasil": MODE_YGGDRASIL, "external": MODE_YGGDRASIL, "authlib": MODE_YGGDRASIL,
    "外置": MODE_YGGDRASIL, "外置登录": MODE_YGGDRASIL, "皮肤站": MODE_YGGDRASIL,
    "offline": MODE_OFFLINE, "cracked": MODE_OFFLINE, "离线": MODE_OFFLINE,
    "离线验证": MODE_OFFLINE, "盗版": MODE_OFFLINE,
    "mixed": MODE_MIXED, "混合": MODE_MIXED, "混合验证": MODE_MIXED,
    "auto": "", "自动": "", "": "",
}

#: 紧凑数组里用的整数编码，配置链接要塞进 QQ 的可点击长度里，能省一个字符是一个。
MODE_TO_CODE: Dict[str, int] = {
    "": 0,
    MODE_OFFICIAL: 1,
    MODE_MUA: 2,
    MODE_YGGDRASIL: 3,
    MODE_OFFLINE: 4,
    MODE_MIXED: 5,
    # 只能追加，不能重排已有编号，否则旧配置链接会错位。
    MODE_XDU: 6,
}
CODE_TO_MODE: Dict[int, str] = {code: mode for mode, code in MODE_TO_CODE.items()}


def style_for(mode: Optional[str]) -> AuthModeStyle:
    """取展示样式，未知值统一落到“未知验证方式”。"""
    return AUTH_MODE_STYLES.get(str(mode or "").strip().lower(), AUTH_MODE_STYLES[MODE_UNKNOWN])


def normalize_mode(value: Any) -> Optional[str]:
    """把用户输入解析成标准值。

    Returns:
        标准值字符串；``""`` 表示“自动 / 清除配置”；``None`` 表示无法识别。
    """
    text = str(value or "").strip().lower()
    if text in MODE_ALIASES:
        return MODE_ALIASES[text]
    if text in CONFIGURABLE_MODES:
        return text
    return None


def mode_to_code(mode: Any) -> int:
    return MODE_TO_CODE.get(str(mode or "").strip().lower(), 0)


def code_to_mode(code: Any) -> str:
    try:
        return CODE_TO_MODE.get(int(code), "")
    except (TypeError, ValueError):
        return ""


# ==============================================================================
# 2. 离线 UUID 推导
# ==============================================================================

def offline_uuid(player_name: str) -> str:
    """算出某个名字在离线模式下的 UUID（32 位小写十六进制，不带连字符）。

    等价于 Java 的 ``UUID.nameUUIDFromBytes(("OfflinePlayer:"+name).getBytes(UTF_8))``：
    取 MD5 摘要后把第 7 字节的高 4 位置成版本号 3、第 9 字节的高 2 位置成
    IETF 变体位。
    """
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{player_name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return uuid_module.UUID(bytes=bytes(digest)).hex


def normalize_uuid(value: Any) -> str:
    """把带/不带连字符的 UUID 统一成 32 位小写十六进制；非法值返回 ``""``。"""
    text = str(value or "").strip().replace("-", "").lower()
    if len(text) != 32:
        return ""
    try:
        int(text, 16)
    except ValueError:
        return ""
    return text


def is_offline_uuid(player_name: str, player_uuid: Any) -> bool:
    """该 (名字, UUID) 是否正好是离线模式推导出来的组合。"""
    normalized = normalize_uuid(player_uuid)
    if not normalized or not player_name:
        return False
    return normalized == offline_uuid(player_name)


# ==============================================================================
# 3. 名字 -> UUID 的外部查询（带缓存）
# ==============================================================================

XDU_YGGDRASIL_ROOT = "https://www.xducraft.cn/api/yggdrasil"
MUA_YGGDRASIL_ROOT = "https://skin.mualliance.ltd/api/union/yggdrasil"
MOJANG_BULK_LOOKUP_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/bulk/byname"

LOOKUP_TIMEOUT = 3.0
#: 整个探测的总预算。超时就返回已经算出来的部分，绝不拖慢出图。
DETECTION_BUDGET = 6.0
#: 一次批量查询最多带多少个名字（样本本身一般不超过 12 个）。
MAX_LOOKUP_NAMES = 24

PROFILE_CACHE_TTL = 30 * 60
PROFILE_CACHE_MAX = 4096
VERDICT_CACHE_TTL = 5 * 60
VERDICT_CACHE_MAX = 512

SOURCE_XDU = "xdu"
SOURCE_MUA = "mua"
SOURCE_MOJANG = "mojang"

# (source, 小写名字) -> (uuid 或 "", 写入时间)。"" 表示查过但该站没有这个名字。
_profile_cache: Dict[Tuple[str, str], Tuple[str, float]] = {}
# ip -> (AuthVerdict, 写入时间)
_verdict_cache: Dict[str, Tuple["AuthVerdict", float]] = {}


@dataclass(frozen=True)
class ProfileLookup:
    """一次名字反查的结果。

    ``completed`` 记录哪些名字已经得到确定答复（包括“查无此人”）。网络失败的
    名字不会放进去，避免把“接口不可用”误当成“已知来源都没有，因此是其他外置站”。
    """

    profiles: Dict[str, str]
    completed: frozenset[str]


def _prune(cache: Dict, max_size: int) -> None:
    """超出上限时按写入时间丢掉最旧的四分之一，避免缓存无限增长。"""
    if len(cache) <= max_size:
        return
    victims = sorted(cache.items(), key=lambda item: item[1][1])[: max(1, len(cache) // 4)]
    for key, _ in victims:
        cache.pop(key, None)


def _cache_get(source: str, name: str) -> Optional[str]:
    entry = _profile_cache.get((source, name.lower()))
    if entry is None:
        return None
    value, stamp = entry
    if time.monotonic() - stamp > PROFILE_CACHE_TTL:
        _profile_cache.pop((source, name.lower()), None)
        return None
    return value


def _cache_put(source: str, name: str, value: str) -> None:
    _profile_cache[(source, name.lower())] = (value, time.monotonic())
    _prune(_profile_cache, PROFILE_CACHE_MAX)


def _parse_profile_list(payload: Any) -> Dict[str, str]:
    """把 ``[{"id": ..., "name": ...}]` 解析成 ``{小写名字: 32位uuid}``。"""
    result: Dict[str, str] = {}
    if not isinstance(payload, list):
        return result
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        profile_uuid = normalize_uuid(item.get("id"))
        if name and profile_uuid:
            result[name.lower()] = profile_uuid
    return result


async def _lookup_uncached(
    source: str,
    names: Sequence[str],
    client: httpx.AsyncClient,
) -> Optional[Dict[str, str]]:
    """向某个数据源批量查名字；请求失败返回 ``None``。"""
    if not names:
        return {}

    try:
        if source == SOURCE_XDU:
            response = await client.post(
                f"{XDU_YGGDRASIL_ROOT}/api/profiles/minecraft",
                json=list(names),
            )
        elif source == SOURCE_MUA:
            response = await client.post(
                f"{MUA_YGGDRASIL_ROOT}/api/profiles/minecraft",
                json=list(names),
            )
        else:
            response = await client.post(MOJANG_BULK_LOOKUP_URL, json=list(names))
        response.raise_for_status()
        return _parse_profile_list(response.json())
    except Exception as exc:
        logger.debug("[AuthMode] {} 批量查询失败: {}", source, exc)
        return None


async def lookup_profiles(
    source: str,
    names: Sequence[str],
    client: httpx.AsyncClient,
) -> ProfileLookup:
    """带缓存的批量查询。只有缓存缺失的名字才会真的发请求。

    命中“查过但不存在”也会被缓存（存 ``""``），避免对同一批离线玩家反复打
    XDU、MUA 和 Mojang 的接口。
    """
    resolved: Dict[str, str] = {}
    completed = set()
    pending: List[str] = []

    for name in names:
        normalized_name = name.lower()
        cached = _cache_get(source, name)
        if cached is None:
            pending.append(name)
            continue

        completed.add(normalized_name)
        if cached:
            resolved[normalized_name] = cached

    if pending:
        fetched = await _lookup_uncached(source, pending[:MAX_LOOKUP_NAMES], client)
        if fetched is not None:
            for name in pending[:MAX_LOOKUP_NAMES]:
                normalized_name = name.lower()
                value = fetched.get(normalized_name, "")
                _cache_put(source, name, value)
                completed.add(normalized_name)
                if value:
                    resolved[normalized_name] = value

    return ProfileLookup(resolved, frozenset(completed))


# ==============================================================================
# 4. 判定
# ==============================================================================

@dataclass
class AuthVerdict:
    """一次探测的结论。"""

    mode: str = MODE_UNKNOWN
    #: 每种模式各命中了几个玩家，用于解释判定依据。
    counts: Dict[str, int] = field(default_factory=dict)
    #: 参与判定的玩家总数（样本里能用的部分）。
    sampled: int = 0
    #: 是否因为超时/断网只跑完了一部分。
    partial: bool = False

    @property
    def conclusive(self) -> bool:
        return self.mode != MODE_UNKNOWN and self.sampled > 0

    def summary(self) -> str:
        """给管理员看的一句话解释。"""
        if not self.conclusive:
            return "样本不足，无法判定"
        parts = [
            f"{style_for(mode).label} {count} 人"
            for mode, count in sorted(self.counts.items(), key=lambda item: -item[1])
            if count
        ]
        detail = "，".join(parts)
        suffix = "（探测未完成，结果可能不全）" if self.partial else ""
        return f"基于 {self.sampled} 个在线玩家样本：{detail}{suffix}"


def _usable_sample(sample: Any) -> List[Tuple[str, str]]:
    """从玩家样本里挑出 (名字, 32位uuid) 都有效的条目。"""
    if not isinstance(sample, (list, tuple)):
        return []

    players: List[Tuple[str, str]] = []
    seen = set()
    for entry in sample:
        if isinstance(entry, dict):
            name = str(entry.get("name", "") or "").strip()
            player_uuid = normalize_uuid(entry.get("id"))
        else:
            name = str(getattr(entry, "name", "") or "").strip()
            player_uuid = normalize_uuid(getattr(entry, "id", None))

        if not name or not player_uuid:
            continue
        # 匿名占位样本（全 0 UUID）不代表真人，直接丢掉。
        if player_uuid == "0" * 32:
            continue
        if player_uuid in seen:
            continue
        seen.add(player_uuid)
        players.append((name, player_uuid))

        if len(players) >= MAX_LOOKUP_NAMES:
            break

    return players


def _aggregate(counts: Dict[str, int]) -> str:
    """把逐玩家的标签聚合成服务器级别的结论。"""
    decided = {mode: count for mode, count in counts.items() if mode != MODE_UNKNOWN and count}
    if not decided:
        return MODE_UNKNOWN
    if len(decided) == 1:
        return next(iter(decided))
    return MODE_MIXED


async def detect_auth_mode(sample: Any, *, client: Optional[httpx.AsyncClient] = None) -> AuthVerdict:
    """从玩家样本推断服务器的登录验证方式。

    判定顺序是刻意的：

    1. **先做离线判定**——它是确定性的、不联网的，也不可能误判；
    2. 并发查询 XDU、MUA 和 Mojang，必须 **名字与 UUID 同时相等**才算命中；
    3. 三个已知源都完成查询且只命中一个，才采用该结论；同时命中多个来源时
       无法从状态协议区分服务器实际使用的认证后端；
    4. 三个已知源都明确答复且都不匹配，才说明是别的外置登录站。

    任何网络异常都只会让结论退化（``partial=True``），不会抛出。
    """
    players = _usable_sample(sample)
    verdict = AuthVerdict(sampled=len(players))
    if not players:
        return verdict

    counts: Dict[str, int] = {}

    def mark(mode: str) -> None:
        counts[mode] = counts.get(mode, 0) + 1

    # --- 第一步：离线判定，纯本地计算 ---
    remaining: List[Tuple[str, str]] = []
    for name, player_uuid in players:
        if player_uuid == offline_uuid(name):
            mark(MODE_OFFLINE)
        else:
            remaining.append((name, player_uuid))

    if not remaining:
        verdict.counts = counts
        verdict.mode = _aggregate(counts)
        return verdict

    # --- 第二步：三个外部源并发查询，整体限时 ---
    #
    # MUA 站偶尔连通性不佳，若按来源串行探测，会白白吃掉一次完整超时并挤压
    # XDU / Mojang 的查询预算。并发后总耗时约等于最慢的那一个，而不是三者相加。
    async def _resolve_remaining() -> None:
        names = [name for name, _ in remaining]
        owns_client = client is None
        active = client or httpx.AsyncClient(timeout=LOOKUP_TIMEOUT)
        try:
            xdu_lookup, mua_lookup, mojang_lookup = await asyncio.gather(
                lookup_profiles(SOURCE_XDU, names, active),
                lookup_profiles(SOURCE_MUA, names, active),
                lookup_profiles(SOURCE_MOJANG, names, active),
            )

            for name, player_uuid in remaining:
                normalized_name = name.lower()
                completed = all(
                    normalized_name in lookup.completed
                    for lookup in (xdu_lookup, mua_lookup, mojang_lookup)
                )
                matches = [
                    mode
                    for mode, lookup in (
                        (MODE_XDU, xdu_lookup),
                        (MODE_MUA, mua_lookup),
                        (MODE_OFFICIAL, mojang_lookup),
                    )
                    if lookup.profiles.get(normalized_name) == player_uuid
                ]

                # MUA 是联合认证，同一个高校站角色可能同时出现在 XDU 和 MUA
                # 的查询结果里。状态响应只给名字和 UUID，无法知道服务端实际加载
                # 的认证地址；必须把这种情况留作未知，而不是按列表顺序猜测。
                if completed and len(matches) == 1:
                    mark(matches[0])
                elif completed and not matches:
                    mark(MODE_YGGDRASIL)
                else:
                    # 接口未完成或同时命中多个来源，都不足以形成唯一结论。
                    mark(MODE_UNKNOWN)
                    verdict.partial = True
        finally:
            if owns_client:
                await active.aclose()

    try:
        await asyncio.wait_for(_resolve_remaining(), timeout=DETECTION_BUDGET)
    except asyncio.TimeoutError:
        verdict.partial = True
        logger.debug("[AuthMode] 探测超时，返回部分结果。")
    except Exception as exc:
        verdict.partial = True
        logger.debug("[AuthMode] 探测异常，返回部分结果: {}", exc)

    verdict.counts = counts
    verdict.mode = _aggregate(counts)
    return verdict


async def detect_for_server(
    ip: str,
    sample: Any,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> AuthVerdict:
    """带服务器级缓存的探测。同一个 IP 在 TTL 内只算一次。"""
    key = str(ip or "").strip().lower()
    now = time.monotonic()

    if key:
        cached = _verdict_cache.get(key)
        if cached is not None:
            verdict, stamp = cached
            if now - stamp <= VERDICT_CACHE_TTL and verdict.conclusive:
                return verdict

    verdict = await detect_auth_mode(sample, client=client)

    # 只缓存有结论的判定：样本为空时缓存“未知”会把后面真有人时的探测也挡掉。
    if key and verdict.conclusive:
        _verdict_cache[key] = (verdict, now)
        _prune(_verdict_cache, VERDICT_CACHE_MAX)

    return verdict


async def annotate_servers(server_nodes: Iterable[Dict[str, Any]]) -> None:
    """给整棵服务器树补上 ``auth_detected`` 字段（原地修改）。

    并发探测所有节点，共用一个 HTTP 连接池；单个节点失败不影响其他节点。
    这个函数**保证不抛异常**——验证方式只是锦上添花，绝不能让状态图发不出来。
    """
    flat: List[Dict[str, Any]] = []

    def walk(nodes: Iterable[Dict[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            flat.append(node)
            children = node.get("children")
            if isinstance(children, list):
                walk(children)

    walk(server_nodes)

    targets = [
        node for node in flat
        if node.get("online") and _usable_sample((node.get("players") or {}).get("sample") if isinstance(node.get("players"), dict) else None)
    ]
    if not targets:
        return

    try:
        async with httpx.AsyncClient(timeout=LOOKUP_TIMEOUT) as client:
            async def annotate(node: Dict[str, Any]) -> None:
                players = node.get("players") if isinstance(node.get("players"), dict) else {}
                verdict = await detect_for_server(
                    str(node.get("ip") or node.get("original_query") or ""),
                    players.get("sample"),
                    client=client,
                )
                if verdict.conclusive:
                    node["auth_detected"] = verdict.mode
                    node["auth_detected_detail"] = verdict.summary()

            await asyncio.gather(*(annotate(node) for node in targets), return_exceptions=True)
    except Exception as exc:
        logger.debug("[AuthMode] 批量探测失败，跳过验证方式标注: {}", exc)


# ==============================================================================
# 5. 配置与探测结果的合成
# ==============================================================================

@dataclass(frozen=True)
class ResolvedAuth:
    """一台服务器最终要展示的验证方式。"""

    mode: str
    origin: str
    #: 配置与实测**不一致**时为真，用于提醒管理员改配置。
    conflict: bool = False
    detected: str = ""
    configured: str = ""

    @property
    def style(self) -> AuthModeStyle:
        return style_for(self.mode)

    @property
    def confirmed(self) -> bool:
        """是否有实测支撑（而不只是写在配置里）。"""
        return self.origin == ORIGIN_DETECTED or (bool(self.detected) and self.detected == self.mode)

    def describe(self) -> str:
        """给 ``/mcs auth`` 用的一行说明。"""
        style = self.style
        if self.mode == MODE_UNKNOWN:
            return "未知验证方式（未配置，且没有可用的玩家样本）"

        origin_text = {
            ORIGIN_DETECTED: "实测确认",
            ORIGIN_CONFIGURED: "管理员配置",
            ORIGIN_INHERITED: "继承自本群默认",
        }.get(self.origin, "未知来源")

        line = f"{style.label}（{origin_text}）"
        if self.conflict:
            line += f"\n  ⚠ 实测结果为 {style_for(self.detected).label}，与配置不一致，建议核对。"
        return line


def resolve_auth(
    server_data: Dict[str, Any],
    group_default: str = "",
) -> ResolvedAuth:
    """合成一台服务器最终展示的验证方式。

    优先级：**管理员配置 > 群默认 > 实测**。

    配置优先是刻意的——样本可能只覆盖了服务器的一部分玩家（比如一个开了
    统一登录的服务器，此刻恰好只有正版玩家在线），管理员知道全貌。
    但只要实测和配置不一致，就把 ``conflict`` 打上，让管理员看得见。
    """
    configured = str(server_data.get("auth_mode") or "").strip().lower()
    if configured not in CONFIGURABLE_MODES:
        configured = ""

    detected = str(server_data.get("auth_detected") or "").strip().lower()
    if detected not in CONFIGURABLE_MODES:
        detected = ""

    inherited = str(group_default or "").strip().lower()
    if inherited not in CONFIGURABLE_MODES:
        inherited = ""

    if configured:
        return ResolvedAuth(
            mode=configured,
            origin=ORIGIN_CONFIGURED,
            conflict=bool(detected and detected != configured),
            detected=detected,
            configured=configured,
        )

    if inherited:
        return ResolvedAuth(
            mode=inherited,
            origin=ORIGIN_INHERITED,
            conflict=bool(detected and detected != inherited),
            detected=detected,
            configured=inherited,
        )

    if detected:
        return ResolvedAuth(mode=detected, origin=ORIGIN_DETECTED, detected=detected)

    return ResolvedAuth(mode=MODE_UNKNOWN, origin=ORIGIN_NONE)


def clear_caches() -> None:
    """仅供测试与手动排查：清空所有缓存。"""
    _profile_cache.clear()
    _verdict_cache.clear()


__all__ = [
    "MODE_XDU", "MODE_MUA", "MODE_OFFICIAL", "MODE_YGGDRASIL", "MODE_OFFLINE", "MODE_MIXED", "MODE_UNKNOWN",
    "CONFIGURABLE_MODES", "AUTH_MODE_STYLES", "AuthModeStyle", "AuthVerdict", "ResolvedAuth",
    "ProfileLookup",
    "ORIGIN_DETECTED", "ORIGIN_CONFIGURED", "ORIGIN_INHERITED", "ORIGIN_NONE",
    "style_for", "normalize_mode", "mode_to_code", "code_to_mode",
    "offline_uuid", "normalize_uuid", "is_offline_uuid",
    "detect_auth_mode", "detect_for_server", "annotate_servers", "resolve_auth",
    "clear_caches", "XDU_YGGDRASIL_ROOT", "MUA_YGGDRASIL_ROOT",
]
