"""下载端口"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol


@dataclass(frozen=True)
class DownloadTask:
    """下载任务（不可变值对象）"""

    url: str  #: 远程下载地址
    filename: str  #: 目标文件名
    destination: str  #: 绝对目录路径（文件将写入 <destination>/<filename>）
    expected_sha1: Optional[str] = None  #: 期望 sha1，非空时下载后必须校验
    status: Literal["pending", "running", "completed", "skipped", "failed"] = (
        "pending"
    )  #: 任务状态


@dataclass(frozen=True)
class DownloadResult:
    """下载结果（不可变值对象）

    失败通过结构化结果而非异常表达，调用方必须检查 success。
    """

    success: bool  #: 是否成功
    filename: str  #: 目标文件名
    path: str = ""  #: 已写入文件的绝对路径（成功/跳过时有值）
    bytes_downloaded: int = 0  #: 实际下载字节数
    error: Optional[str] = None  #: 错误消息（失败时）
    error_code: Optional[str] = None  #: 错误码（失败时，如 E301）
    retries: int = 0  #: 实际重试次数
    skipped: bool = False  #: 是否因已存在/校验通过而跳过


class ProgressCallback(Protocol):
    """下载进度回调

    实现期望：
        - 下载期间周期性回调，报告 filename 的已下载字节数 downloaded 与总大小 total
        - total 未知时传 0；回调为 async，下载器应等待其完成
    """

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
        """下载单个任务；失败通过 DownloadResult 返回而非静默吞没

        实现期望：
            - 将文件写入 task.destination/<task.filename>（必要时创建目录）
            - task.expected_sha1 非空时下载后校验，不匹配视为失败
            - 失败返回 success=False 并填 error/error_code；禁止抛异常
        """
        ...

    async def close(self) -> None:
        """释放底层资源（连接池等）；实现必须可重复安全调用"""
        ...
