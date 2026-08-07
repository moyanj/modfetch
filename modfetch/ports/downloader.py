"""下载端口"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol


@dataclass(frozen=True)
class DownloadTask:
    """下载任务（不可变值对象）"""

    url: str
    filename: str
    destination: str  # 绝对目录路径
    expected_sha1: Optional[str] = None
    status: Literal["pending", "running", "completed", "skipped", "failed"] = (
        "pending"
    )


@dataclass(frozen=True)
class DownloadResult:
    """下载结果（不可变值对象）"""

    success: bool
    filename: str
    path: str = ""
    bytes_downloaded: int = 0
    error: Optional[str] = None
    error_code: Optional[str] = None
    retries: int = 0
    skipped: bool = False


class ProgressCallback(Protocol):
    """下载进度回调"""

    async def __call__(
        self, filename: str, downloaded: int, total: int
    ) -> None:
        ...


class DownloaderPort(Protocol):
    """下载器接口：单任务下载语义，队列编排在应用层"""

    async def download(
        self,
        task: DownloadTask,
        progress: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """下载单个任务；失败通过 DownloadResult 返回而非静默吞没"""
        ...

    async def close(self) -> None:
        """释放底层资源"""
        ...
