"""向后兼容 shim — 下载组件已迁入 modfetch.adapters.download

旧 DownloadManager/DownloadQueue 已删除，由 DownloadExecutor/HttpDownloader 替代。
"""

from modfetch.adapters.download import (  # noqa: F401
    DownloadExecutor,
    ExecutionReport,
    FileArtifactStore,
    HttpDownloader,
    LocalFileCopier,
    RetryPolicy,
)
from modfetch.adapters.download.verifier import FileVerifier  # noqa: F401

__all__ = [
    "DownloadExecutor",
    "ExecutionReport",
    "FileArtifactStore",
    "HttpDownloader",
    "LocalFileCopier",
    "RetryPolicy",
    "FileVerifier",
]
