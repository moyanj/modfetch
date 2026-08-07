"""
文件校验器

实现 SHA1 校验、文件存在性检查、文件完整性验证（纯静态方法）。
"""

import hashlib
import os
from typing import Optional

import aiofiles


class FileVerifier:
    """文件校验器"""

    @staticmethod
    async def calc_sha1(file_path: str) -> Optional[str]:
        """计算文件的 SHA1 值；文件不存在或读取失败返回 None"""
        if not os.path.exists(file_path):
            return None

        sha1 = hashlib.sha1()
        try:
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    data = await f.read(4096)
                    if not data:
                        break
                    sha1.update(data)
            return sha1.hexdigest()
        except (IOError, OSError):
            return None

    @staticmethod
    async def verify_sha1(file_path: str, expected_sha1: Optional[str]) -> bool:
        """校验 SHA1；无预期值视为通过"""
        if not expected_sha1:
            return True

        current_sha1 = await FileVerifier.calc_sha1(file_path)
        if current_sha1 is None:
            return False

        return current_sha1 == expected_sha1

    @staticmethod
    def exists(file_path: str) -> bool:
        """检查文件是否存在"""
        return os.path.exists(file_path)

    @staticmethod
    def get_size(file_path: str) -> int:
        """获取文件大小"""
        try:
            return os.path.getsize(file_path)
        except (IOError, OSError):
            return 0

    @staticmethod
    async def is_valid(file_path: str, expected_sha1: Optional[str] = None) -> bool:
        """检查文件是否有效（存在且校验通过）"""
        if not FileVerifier.exists(file_path):
            return False

        if expected_sha1:
            return await FileVerifier.verify_sha1(file_path, expected_sha1)

        return True
