"""文件制品存储（ArtifactStorePort 实现）

把"下载结果写到哪里、如何校验"抽象为存储端口，使下载器
不依赖具体文件系统细节。本实现针对本地文件系统：
- 流式写入（经 aiofiles 异步 IO）
- SHA1 校验（委托 FileVerifier）
- 路径安全校验（防目录穿越）
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Dict

import aiofiles

from modfetch.adapters.download.verifier import FileVerifier


class FileArtifactStore:
    """本地文件系统制品存储（ArtifactStorePort 实现）"""

    async def exists(self, path: Path) -> bool:
        """文件是否存在"""
        return path.exists()

    async def write(self, path: Path, source: AsyncIterator[bytes]) -> int:
        """流式写入，返回字节数；自动创建父目录

        采用边读边写的流式方式而非一次性读入内存，避免大文件
        （模组 jar 可达百 MB 级）占用过多内存。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        async with aiofiles.open(path, "wb") as f:
            async for chunk in source:
                await f.write(chunk)
                written += len(chunk)
        return written

    async def verify(self, path: Path, hashes: Dict[str, str]) -> bool:
        """校验 sha1（若提供）；空哈希集合视为通过

        Args:
            path: 待校验文件
            hashes: 哈希集合（当前仅使用 sha1 键）

        Returns:
            文件存在且哈希匹配为 True；文件缺失直接返回 False；
            未提供哈希时视为通过（调用方不要求校验）。
        """
        if not path.exists():
            return False
        sha1 = hashes.get("sha1")
        if sha1:
            return await FileVerifier.verify_sha1(str(path), sha1)
        return True

    def safe_path(self, base: Path, filename: str) -> Path:
        """解析 base/filename 并校验不穿越 base 目录

        安全动机：filename 可能来自远端元数据（如 Modrinth 返回的
        文件名），恶意构造的 ``../`` 或绝对路径可把文件写到
        base 目录之外。故先 resolve 规范化符号链接与 ``..``，
        再确认结果仍在 base 目录树内。

        Raises:
            ValueError: filename 为绝对路径或解析后越出 base
        """
        if os.path.isabs(filename):
            raise ValueError(f"非法文件名（绝对路径）: {filename}")
        resolved = (base / filename).resolve()
        base_resolved = base.resolve()
        if resolved != base_resolved and base_resolved not in resolved.parents:
            raise ValueError(f"非法文件名（目录穿越）: {filename}")
        return resolved
