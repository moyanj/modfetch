"""下载适配器

下载链路各环节的实现：重试策略（RetryPolicy）、文件校验
（FileVerifier）、制品存储（FileArtifactStore）、HTTP 下载执行
（HttpDownloader）、本地文件复制（LocalFileCopier）以及并发编排
（DownloadExecutor/ExecutionReport）。
对外统一导出，供 application 层与 Web 层组装使用。
"""

from modfetch.adapters.download.retry import RetryPolicy
from modfetch.adapters.download.verifier import FileVerifier
from modfetch.adapters.download.file_store import FileArtifactStore
from modfetch.adapters.download.http_downloader import HttpDownloader
from modfetch.adapters.download.local_copier import LocalFileCopier
from modfetch.adapters.download.executor import DownloadExecutor, ExecutionReport

__all__ = [
    "RetryPolicy",
    "FileVerifier",
    "FileArtifactStore",
    "HttpDownloader",
    "LocalFileCopier",
    "DownloadExecutor",
    "ExecutionReport",
]
