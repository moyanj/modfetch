"""
依赖组装（Composition Root）

CLI 与 Web 共用：构建 BuildApplicationService 及其全部适配器依赖。
"""

from typing import Optional

from modfetch.adapters.caching import CachingCatalog
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
from modfetch.ports.catalog import CatalogPort
from modfetch.ports.event_sink import EventSink


def create_build_service(
    event_sink: Optional[EventSink] = None,
    max_concurrent: int = 5,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    verify_ssl: bool = True,
    catalog: Optional[CatalogPort] = None,
) -> BuildApplicationService:
    """组装 BuildApplicationService

    依赖图（注入顺序自底向上）：
        ModrinthClient(catalog) ──┬─→ PlanBuild ─────────┐
                                  │                      ├─→ BuildApplicationService
        FileArtifactStore ─→ HttpDownloader ─→ ExecuteBuild┘
        RetryPolicy ────────────↗                │
        PackagerDispatcher(mrpack/zip) ──────────↗
        LogEventSink/自定义 event_sink ─────────→ BuildApplicationService
        ConfigService ─────────────────────────→ BuildApplicationService

    Args:
        event_sink: 事件接收器（默认 LogEventSink）
        max_concurrent: 下载并发数
        max_retries: 下载重试次数
        retry_delay: 重试基础延迟
        verify_ssl: 是否校验 TLS（默认开启）
        catalog: 自定义 CatalogPort（测试注入用）
    """
    # 默认 catalog：生产走 ModrinthClient，测试注入 stub 实现（对应 CatalogPort）
    base_catalog: CatalogPort = catalog or ModrinthClient()
    # 请求聚合缓存：包装 catalog，消除多 target/多模组间的重复外部请求
    # （get_project/get_version/get_loader_version），且 negative 结果一并缓存。
    # 生命周期即本次组装，Web 端每个 job 重新组装并 close，不跨 job 污染。
    cached_catalog = CachingCatalog(base_catalog)

    # 制品存储（ArtifactStorePort）：文件落盘与哈希校验的基础设施
    store = FileArtifactStore()
    # 重试策略：下载重试次数与基础延迟
    retry = RetryPolicy(max_retries=max_retries, base_delay=retry_delay)
    # 下载器（DownloaderPort）：将任务写入 store，失败按 retry 重试，受 verify_ssl 约束
    downloader = HttpDownloader(
        retry_policy=retry,
        artifact_store=store,
        verify_ssl=verify_ssl,
    )

    # 加载器版本解析闭包：mrpack 打包需要的最新 loader 版本，委托给 catalog
    async def loader_version_resolver(loader, mc_version: str):
        return await cached_catalog.get_loader_version(loader.value, mc_version)

    # 打包器（PackagerPort）分派：按 format 路由到 mrpack/zip 具体实现
    packager = PackagerDispatcher(
        {
            "mrpack": MrpackPackager(
                loader_version_resolver=loader_version_resolver
            ),
            "zip": ZipPackager(),
        }
    )

    # 配置服务：统一配置边界（解析/校验）
    config_service = ConfigService()
    # 计划生成用例：解析配置为 BuildPlan（依赖 catalog 与依赖图解析器）
    plan_build = PlanBuild(cached_catalog, DependencyGraphResolver(cached_catalog))
    # 执行用例：按计划下载（受并发限制）并交给打包器产出制品
    execute_build = ExecuteBuild(
        downloader, packager, max_concurrent=max_concurrent
    )
    # 事件接收器：默认写日志，可注入作业/复合接收器（EventSink）
    sink = event_sink or LogEventSink()

    # 应用服务：统一入口，串起配置/计划/执行/事件四个用例
    return BuildApplicationService(
        config_service=config_service,
        plan_build=plan_build,
        execute_build=execute_build,
        event_sink=sink,
        # 构建结束需释放的资源：catalog 与 downloader 各自持有
        # aiohttp session，由 BuildApplicationService.close() 统一关闭
        closables=(cached_catalog, downloader),
    )
