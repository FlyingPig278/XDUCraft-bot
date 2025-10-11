import base64
import hashlib
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Union

import httpx

# 缓存配置
SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = SCRIPT_DIR / "image_cache"
CACHE_TTL = 60 * 60  # 缓存有效期：60分钟（秒）
CACHE_DIR.mkdir(exist_ok=True)

def get_cache_path(url: str) -> Path:
    """生成缓存文件路径（使用URL的SHA256哈希）"""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.cache"


def is_cache_valid(cache_path: Path) -> bool:
    """检查缓存是否有效（存在且未过期）"""
    if not cache_path.exists():
        return False

    # 检查文件修改时间
    file_age = time.time() - cache_path.stat().st_mtime
    return file_age < CACHE_TTL


def read_from_cache(cache_path: Path) -> Union[None, BytesIO]:
    """从缓存读取图片数据"""
    try:
        with open(cache_path, "rb") as f:
            print(f"使用缓存图片: {cache_path.name}")
            return BytesIO(f.read())
    except IOError as e:
        print(f"读取缓存失败 {cache_path}: {e}")
        return None


def write_to_cache(cache_path: Path, data: bytes) -> bool:
    """将图片数据写入缓存（使用原子重命名确保完整性）"""
    temp_path = cache_path.with_suffix(".tmp")
    try:
        # 1. 写入临时文件
        temp_path.write_bytes(data)

        # 2. 原子性重命名
        temp_path.replace(cache_path)
        print(f"已缓存图片: {cache_path.name}")
        return True
    except IOError as e:
        print(f"写入缓存失败 {cache_path}: {e}")
        # 清理可能的临时文件
        temp_path.unlink(missing_ok=True)
        return False


async def download_image_with_cache(url: str) -> Union[None, BytesIO]:
    """下载图片并使用缓存"""
    cache_path = get_cache_path(url)

    # 1. 检查缓存是否有效
    if is_cache_valid(cache_path):
        cached_data = read_from_cache(cache_path)
        if cached_data:
            return cached_data

    # 2. 缓存无效或不存在，从网络下载
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            response.raise_for_status()
            image_data = response.content

            # 3. 保存到缓存
            write_to_cache(cache_path, image_data)

            return BytesIO(image_data)
    except httpx.RequestError as e:
        print(f"下载图片失败 {url}: {e}")
        return None
    except Exception as e:
        print(f"处理图片URL时发生错误 {url}: {e}")
        return None


def decode_base64_data(data_uri: str) -> Union[None, BytesIO]:
    """解码Base64数据URI"""
    match = re.search(r"data:image/(?P<ext>.*?);base64,(?P<data>.*)", data_uri, re.DOTALL)
    if not match:
        return None

    try:
        data = match.groupdict().get("data")
        if not data:
            print("Base64数据为空")
            return None

        decoded_data = base64.b64decode(data)
        return BytesIO(decoded_data)
    except ValueError as e:
        print(f"Base64解码失败: {e}")
        return None


async def decode_image(src: str) -> Union[None, BytesIO]:
    """
    从Base64数据URI或远程URL解码图像
    对URL使用缓存，有效期60分钟
    """
    # 1. 检查是否是Base64数据URI
    if src.startswith("data:image/"):
        return decode_base64_data(src)

    # 2. 处理URL（使用缓存）
    return await download_image_with_cache(src)


# 缓存管理功能
def cleanup_expired_cache():
    """清理过期的缓存文件"""
    current_time = time.time()
    removed_count = 0

    for cache_file in CACHE_DIR.glob("*.cache"):
        file_age = current_time - cache_file.stat().st_mtime
        if file_age > CACHE_TTL:
            try:
                cache_file.unlink()
                removed_count += 1
            except IOError as e:
                print(f"删除缓存文件失败 {cache_file}: {e}")

    if removed_count > 0:
        print(f"清理了 {removed_count} 个过期缓存文件")


def get_cache_stats():
    """获取缓存统计信息"""
    cache_files = list(CACHE_DIR.glob("*.cache"))
    total_size = sum(f.stat().st_size for f in cache_files)
    valid_files = [f for f in cache_files if is_cache_valid(f)]

    return {
        "total_files": len(cache_files),
        "valid_files": len(valid_files),
        "total_size": total_size,
        "total_size_mb": total_size / (1024 * 1024)
    }

# 在模块加载时执行一次清理
cleanup_expired_cache()