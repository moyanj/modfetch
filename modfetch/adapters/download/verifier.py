"""
文件校验器

实现 SHA1 校验、文件存在性检查、文件完整性验证（纯静态方法）。
SHA1 用于校验下载内容与 Modrinth 元数据中的预期哈希是否一致，
防止下载到损坏或被篡改的文件。
"""

import hashlib
import os
from typing import Optional

import aiofiles


class FileVerifier:
    """文件校验器（全部为静态方法，无实例状态）"""

    @staticmethod
    async def calc_sha1(file_path: str) -> Optional[str]:
        """计算文件的 SHA1 值；文件不存在或读取失败返回 None

        分块（4096 字节）读取并增量更新哈希，避免一次性读入
        大文件占用过多内存。读取失败返回 None 而非抛异常，
        由调用方按"无法校验"处理。
        """
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
            # 读取中途失败（如文件被占用/权限不足）→ 无法校验
            return None

    @staticmethod
    async def verify_sha1(file_path: str, expected_sha1: Optional[str]) -> bool:
        """校验 SHA1；无预期值视为通过

        Args:
            file_path: 待校验文件
            expected_sha1: 期望的 SHA1 值；为空时跳过校验

        Returns:
            哈希一致为 True；无预期值视为通过；文件无法读取
            或哈希不一致为 False
        """
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
        """获取文件大小

        Returns:
            文件字节数；文件不存在或读取失败返回 0
        """
        try:
            return os.path.getsize(file_path)
        except (IOError, OSError):
            return 0

    @staticmethod
    async def is_valid(file_path: str, expected_sha1: Optional[str] = None) -> bool:
        """检查文件是否有效（存在且校验通过）

        组合语义：文件必须存在；若提供了 expected_sha1 则进一步
        校验哈希一致。用于下载前判断"是否可跳过"。
        """
        if not FileVerifier.exists(file_path):
            return False

        if expected_sha1:
            return await FileVerifier.verify_sha1(file_path, expected_sha1)

        return True
