"""带缓存与原子写入的 JSON 配置存储。

各插件原先都各写了一份 ``open() -> json.load() -> json.dump()``：

- 写入不是原子的，进程在写一半时被杀会直接留下损坏的 JSON；
- 每次读取都重新解析整个文件，一次 ``/mcs`` 会重复读几十次；
- 读-改-写之间没有锁，两个并发指令会互相覆盖。

``JsonStore`` 用一份实现解决这三件事，插件只需要提供默认值工厂和
（可选的）归一化函数。
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from threading import RLock
from typing import Any, Callable, Generic, Optional, TypeVar

from nonebot.log import logger

T = TypeVar("T")

_JSONC_SENTINEL = "//"


def strip_json_comments(text: str) -> str:
    """去掉 ``//`` 行注释，让仓库里的 ``*.json.example`` 也能被直接读取。

    只处理行首（允许前导空白）的注释，不去动字符串内部的 ``//``，
    因此 URL 之类的值不会被误伤。
    """
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith(_JSONC_SENTINEL):
            continue
        lines.append(line)
    return "\n".join(lines)


class JsonStore(Generic[T]):
    """单个 JSON 文件的线程安全读写封装。

    Args:
        path: JSON 文件路径。父目录会被自动创建。
        default_factory: 文件缺失/损坏时返回的默认数据。
        normalizer: 可选的归一化函数，每次读入与写出前都会调用，
            用于补齐缺失字段、纠正类型。必须返回一个新的（或原地修正后的）对象。
        allow_comments: 是否容忍 ``//`` 行注释。
    """

    def __init__(
        self,
        path: str,
        default_factory: Callable[[], T],
        normalizer: Optional[Callable[[Any], T]] = None,
        *,
        allow_comments: bool = False,
    ) -> None:
        self.path = os.path.abspath(path)
        self._default_factory = default_factory
        self._normalizer = normalizer
        self._allow_comments = allow_comments
        self._lock = RLock()
        self._cache: Optional[T] = None
        self._cache_stamp: Optional[tuple] = None

    # --- 内部工具 ---

    def _normalize(self, raw: Any) -> T:
        if self._normalizer is None:
            return raw  # type: ignore[return-value]
        try:
            return self._normalizer(raw)
        except Exception as exc:  # 归一化本身不该让整个指令炸掉
            logger.warning("[JsonStore] 归一化 {} 失败，回退默认值: {}", self.path, exc)
            return self._default_factory()

    def _stamp(self) -> Optional[tuple]:
        """用 (mtime_ns, size) 作为缓存指纹。

        单用 mtime 在部分文件系统上分辨率不足，叠加 size 能挡掉绝大多数
        “同一毫秒内被改写且长度不同”的情况。
        """
        try:
            stat = os.stat(self.path)
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _read_from_disk(self) -> T:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            return self._default_factory()
        except OSError as exc:
            logger.error("[JsonStore] 读取 {} 失败: {}", self.path, exc)
            return self._default_factory()

        if self._allow_comments:
            text = strip_json_comments(text)

        if not text.strip():
            return self._default_factory()

        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("[JsonStore] {} 不是合法 JSON（{}），本次使用默认值。", self.path, exc)
            return self._default_factory()

        return self._normalize(raw)

    # --- 对外接口 ---

    def load(self) -> T:
        """读取数据。文件未变化时直接命中内存缓存。

        返回的是缓存对象的深拷贝，调用方随便改都不会污染缓存。
        """
        with self._lock:
            stamp = self._stamp()
            if self._cache is None or stamp != self._cache_stamp:
                self._cache = self._read_from_disk()
                self._cache_stamp = stamp
            return deepcopy(self._cache)

    def save(self, data: T) -> T:
        """归一化后原子写入，并刷新缓存。返回真正落盘的数据。"""
        normalized = self._normalize(data)
        with self._lock:
            directory = os.path.dirname(self.path) or "."
            os.makedirs(directory, exist_ok=True)

            # 同目录建临时文件，保证 os.replace 是同一分区上的原子操作。
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=os.path.basename(self.path) + ".",
                suffix=".tmp",
                delete=False,
            )
            temp_path = handle.name
            try:
                with handle:
                    json.dump(normalized, handle, indent=4, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
            except Exception:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise

            self._cache = deepcopy(normalized)
            self._cache_stamp = self._stamp()
            return deepcopy(normalized)

    def mutate(self, mutator: Callable[[T], Any]) -> Any:
        """在锁内完成一次读-改-写，避免并发指令互相覆盖。

        ``mutator`` 收到当前数据（可原地修改），它的返回值会原样透传给调用方，
        方便返回 “是否真的发生了变化”。数据始终会被写回。
        """
        with self._lock:
            data = self.load()
            result = mutator(data)
            self.save(data)
            return result

    def invalidate(self) -> None:
        """丢弃内存缓存，强制下次 load 重新读盘。"""
        with self._lock:
            self._cache = None
            self._cache_stamp = None


def as_int(value: Any, default: int = 0, *, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    """把任意值尽力转成 int，并夹在 [minimum, maximum] 之间。"""
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def as_str(value: Any, default: str = "") -> str:
    """把任意值尽力转成去掉首尾空白的 str。``None`` 视为缺省。"""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def as_bool(value: Any, default: bool = False) -> bool:
    """把 JSON 里可能出现的各种“真值”写法转成 bool。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on", "是", "开", "开启"}:
            return True
        if lowered in {"false", "0", "no", "n", "off", "否", "关", "关闭"}:
            return False
    return default


def unique_ints(values: Any) -> list:
    """把任意可迭代对象归一化为“去重且保序”的 int 列表。"""
    if not isinstance(values, (list, tuple, set)):
        return []
    result = []
    seen = set()
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


__all__ = [
    "JsonStore",
    "strip_json_comments",
    "as_int",
    "as_str",
    "as_bool",
    "unique_ints",
]
