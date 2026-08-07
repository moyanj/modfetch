"""制品存储端口"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Dict, Protocol

#: 哈希集合，如 {"sha1": "...", "sha512": "..."}
HashSet = Dict[str, str]


class ArtifactStorePort(Protocol):
    """制品文件存储接口

    契约约定：所有路径操作均以 Path 为绝对路径语义，实现负责底层文件系统访问。
    """

    async def exists(self, path: Path) -> bool:
        """文件是否存在

        实现期望：返回 path 指向的常规文件是否存在；目录或不存在返回 False
        """
        ...

    async def write(self, path: Path, source: AsyncIterator[bytes]) -> int:
        """将字节流写入路径，返回写入字节数

        实现期望：
            - 逐块消费 source 并写入 path（必要时创建父目录）
            - 返回实际写入的字节总数；写入失败应抛出异常（不可静默）
        """
        ...

    async def verify(self, path: Path, hashes: HashSet) -> bool:
        """校验文件哈希（支持 sha1/sha512；空集合视为通过）

        实现期望：
            - 对 path 计算 hashes 中列出的算法并逐一比对
            - 任一不匹配返回 False；hashes 为空返回 True（视为通过）
        """
        ...

    def safe_path(self, base: Path, filename: str) -> Path:
        """解析 base/filename 并校验不穿越 base 目录

        Raises:
            ValueError: filename 为绝对路径或含 .. 穿越

        实现期望：返回 base 目录内的安全路径，杜绝路径穿越
        """
        ...
