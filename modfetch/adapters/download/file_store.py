"""文件制品存储（ArtifactStorePort 实现）"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Dict

import aiofiles

from modfetch.adapters.download.verifier import FileVerifier


class FileArtifactStore:
    """本地文件系统制品存储"""

    async def exists(self, path: Path) -> bool:
        return path.exists()

    async def write(self, path: Path, source: AsyncIterator[bytes]) -> int:
        """流式写入，返回字节数；自动创建父目录"""
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        async with aiofiles.open(path, "wb") as f:
            async for chunk in source:
                await f.write(chunk)
                written += len(chunk)
        return written

    async def verify(self, path: Path, hashes: Dict[str, str]) -> bool:
        """校验 sha1（若提供）；空哈希集合视为通过"""
        if not path.exists():
            return False
        sha1 = hashes.get("sha1")
        if sha1:
            return await FileVerifier.verify_sha1(str(path), sha1)
        return True

    def safe_path(self, base: Path, filename: str) -> Path:
        """解析 base/filename 并校验不穿越 base 目录

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
