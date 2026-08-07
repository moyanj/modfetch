"""制品存储端口"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Dict, Protocol

#: 哈希集合，如 {"sha1": "...", "sha512": "..."}
HashSet = Dict[str, str]


class ArtifactStorePort(Protocol):
    """制品文件存储接口"""

    async def exists(self, path: Path) -> bool:
        """文件是否存在"""
        ...

    async def write(self, path: Path, source: AsyncIterator[bytes]) -> int:
        """将字节流写入路径，返回写入字节数"""
        ...

    async def verify(self, path: Path, hashes: HashSet) -> bool:
        """校验文件哈希（支持 sha1/sha512；空集合视为通过）"""
        ...

    def safe_path(self, base: Path, filename: str) -> Path:
        """解析 base/filename 并校验不穿越 base 目录

        Raises:
            ValueError: filename 为绝对路径或含 .. 穿越
        """
        ...
