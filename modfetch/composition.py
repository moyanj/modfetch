"""
依赖组装（Composition Root）

CLI 与 Web 共用：构建 BuildApplicationService 及其全部适配器依赖。
"""

from typing import Optional

from modfetch.adapters.download import (
    FileArtifactStore,
    HttpDownloader,
    RetryPolicy,
)
from modfetch.adapters.events import LogEventSink
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.adapters.packaging import (
    MrpackPackager,
    PackagerDispatcher,
    ZipPackager,
)
from modfetch.application.build_service import BuildApplicationService
from modfetch.application.config_service import ConfigService
from modfetch.application.dependency_resolver import DependencyGraphResolver
from modfetch.application.execute_build import ExecuteBuild
from modfetch.application.plan_build import PlanBuild
from modfetch.ports.event_sink import EventSink


def create_build_service(
    event_sink: Optional[EventSink] = None,
    max_concurrent: int = 5,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    verify_ssl: bool = True,
    catalog: Optional[ModrinthClient] = None,
) -> BuildApplicationService:
    """组装 BuildApplicationService

    Args:
        event_sink: 事件接收器（默认 LogEventSink）
        max_concurrent: 下载并发数
        max_retries: 下载重试次数
        retry_delay: 重试基础延迟
        verify_ssl: 是否校验 TLS（默认开启）
        catalog: 自定义 CatalogPort（测试注入用）
    """
    catalog = catalog or ModrinthClient()

    store = FileArtifactStore()
    retry = RetryPolicy(max_retries=max_retries, base_delay=retry_delay)
    downloader = HttpDownloader(
        retry_policy=retry,
        artifact_store=store,
        verify_ssl=verify_ssl,
    )

    async def loader_version_resolver(loader, mc_version: str):
        return await catalog.get_loader_version(loader.value, mc_version)

    packager = PackagerDispatcher(
        {
            "mrpack": MrpackPackager(
                loader_version_resolver=loader_version_resolver
            ),
            "zip": ZipPackager(),
        }
    )

    config_service = ConfigService()
    plan_build = PlanBuild(catalog, DependencyGraphResolver(catalog))
    execute_build = ExecuteBuild(
        downloader, packager, max_concurrent=max_concurrent
    )
    sink = event_sink or LogEventSink()

    return BuildApplicationService(
        config_service=config_service,
        plan_build=plan_build,
        execute_build=execute_build,
        event_sink=sink,
    )
