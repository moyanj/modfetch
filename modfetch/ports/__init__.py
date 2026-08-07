"""
端口层

定义应用层与外部世界之间的接口（Protocol）。
适配层（adapters/）提供具体实现，应用层（application/）只依赖这些接口。
"""

from modfetch.ports.catalog import CatalogPort
from modfetch.ports.downloader import (
    DownloadResult,
    DownloadTask,
    DownloaderPort,
    ProgressCallback,
)
from modfetch.ports.artifact_store import ArtifactStorePort
from modfetch.ports.packager import PackagerPort
from modfetch.ports.event_sink import EventSink
from modfetch.ports.config_source import ConfigSource
from modfetch.ports.job_repository import (
    JobRecord,
    JobRepository,
    JobSnapshot,
)

__all__ = [
    "CatalogPort",
    "DownloaderPort",
    "DownloadTask",
    "DownloadResult",
    "ProgressCallback",
    "ArtifactStorePort",
    "PackagerPort",
    "EventSink",
    "ConfigSource",
    "JobRepository",
    "JobRecord",
    "JobSnapshot",
]
