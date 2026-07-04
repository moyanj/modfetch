"""
事件桥接层

将 modfetch 插件 Hook 系统转换为 WebSocket 事件流。

包含三个核心组件:
- EventDownloadManager: DownloadManager 子类，在下载过程中触发 Hook
- ServerOrchestrator: ModFetchOrchestrator 子类，集成事件桥接
- EventBridgePlugin: 插件子类，注册全部 14 个 Hook 处理器
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, Optional

import aiohttp
from loguru import logger

from modfetch.download import DownloadManager
from modfetch.models import ModFetchConfig, ModLoader
from modfetch.models.api import ProjectInfo, VersionInfo
from modfetch.orchestrator import ModFetchOrchestrator
from modfetch.plugins.base import (
    HookContext,
    HookResult,
    HookType,
    ModFetchPlugin,
    PluginManager,
)

# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

#: 事件广播回调 — 接收事件字典并推送到所有 WebSocket 订阅者
EventBroadcaster = Callable[[dict[str, object]], Awaitable[None]]

#: 下载事件回调 — (事件类型, 文件名, url 或错误信息)
DownloadEventCallback = Callable[[str, str, Optional[str]], Awaitable[None]]


# ---------------------------------------------------------------------------
# EventDownloadManager
# ---------------------------------------------------------------------------


class EventDownloadManager(DownloadManager):
    """
    DownloadManager 子类

    在每个文件下载前后触发 Hook 事件，使 EventBridgePlugin 能捕获
    PRE_DOWNLOAD / POST_DOWNLOAD / DOWNLOAD_FAILED 事件。
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        session: Optional[aiohttp.ClientSession] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        download_event_callback: Optional[DownloadEventCallback] = None,
    ):
        super().__init__(
            max_concurrent=max_concurrent,
            max_retries=max_retries,
            retry_delay=retry_delay,
            session=session,
            progress_callback=progress_callback,
        )
        self._download_event_callback = download_event_callback

    async def download_file(
        self,
        url: str,
        filename: str,
        download_dir: str,
        expected_sha1: Optional[str] = None,
    ) -> bool:
        """下载单个文件，在前后触发事件"""
        if self._download_event_callback:
            await self._download_event_callback("start", filename, url)

        try:
            result = await super().download_file(
                url, filename, download_dir, expected_sha1
            )
            if self._download_event_callback:
                await self._download_event_callback("complete", filename, None)
            return result
        except Exception as e:
            if self._download_event_callback:
                await self._download_event_callback("failed", filename, str(e))
            raise


# ---------------------------------------------------------------------------
# ServerOrchestrator
# ---------------------------------------------------------------------------


class ServerOrchestrator(ModFetchOrchestrator):
    """
    ModFetchOrchestrator 子类

    - 使用 EventDownloadManager 替代标准 DownloadManager
    - 覆写 _on_download_progress 以触发 DOWNLOAD_PROGRESS Hook
    - 在下载阶段前后广播 phase_change 事件
    - 更新 JobContext 中的当前版本/加载器信息
    """

    def __init__(
        self,
        config: ModFetchConfig,
        plugin_manager: Optional[PluginManager] = None,
        broadcaster: Optional[EventBroadcaster] = None,
        on_version_loader: Optional[Callable[[str, str], None]] = None,
    ):
        super().__init__(config, plugin_manager)
        self._broadcaster = broadcaster
        self._on_version_loader = on_version_loader

    # -- 下载进度 → DOWNLOAD_PROGRESS Hook -------------------------------

    def _on_download_progress(self, filename: str, percent: float) -> None:
        """覆写：将同步进度回调转换为异步 Hook 执行"""
        asyncio.ensure_future(
            self._execute_hook(
                HookType.DOWNLOAD_PROGRESS,
                extra_data={"filename": filename, "percent": percent},
            )
        )

    # -- 下载事件回调 → PRE_DOWNLOAD / POST_DOWNLOAD / DOWNLOAD_FAILED ----

    async def _on_download_event(
        self,
        event_type: str,
        filename: str,
        url_or_error: Optional[str],
    ) -> None:
        """将 EventDownloadManager 的事件转换为 Hook"""
        if event_type == "start":
            await self._execute_hook(
                HookType.PRE_DOWNLOAD,
                extra_data={"filename": filename, "url": url_or_error or ""},
            )
        elif event_type == "complete":
            await self._execute_hook(
                HookType.POST_DOWNLOAD,
                extra_data={"filename": filename},
            )
        elif event_type == "failed":
            await self._execute_hook(
                HookType.DOWNLOAD_FAILED,
                extra_data={
                    "filename": filename,
                    "error": url_or_error or "",
                    "retries": self.config.max_retries,
                },
            )

    # -- 覆写 _process_version 以使用 EventDownloadManager ----------------

    async def _process_version(self, version: str, loader: ModLoader) -> None:
        """
        覆写父类方法，使用 EventDownloadManager 并广播 phase_change 事件。

        逻辑与父类一致，仅替换 DownloadManager 并添加事件广播。
        """
        logger.info(f"准备下载目录 for {version}-{loader.value}")

        # 通知 JobContext 当前版本/加载器
        if self._on_version_loader:
            self._on_version_loader(version, loader.value)

        version_dir = os.path.join(
            self.config.output.download_dir,
            f"{version}-{loader.value}",
        )
        os.makedirs(version_dir, exist_ok=True)
        logger.success(f"目录设定成功: {version_dir}")

        # 使用 EventDownloadManager 替代标准 DownloadManager
        self.download_manager = EventDownloadManager(
            max_concurrent=self.config.max_concurrent,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            progress_callback=self._on_download_progress,
            download_event_callback=self._on_download_event,
        )

        await self._process_mods(version, loader, version_dir)
        await self._process_resourcepacks(version, loader, version_dir)
        await self._process_shaderpacks(version, loader, version_dir)
        await self._process_extra_urls(version, version_dir)

        # 广播 phase_change → download
        if self._broadcaster:
            await self._broadcaster(
                {"event": "phase_change", "data": {"phase": "download"}}
            )

        logger.info(f"启动下载 ({self.config.max_concurrent}并发)...")
        await self.download_manager.run()

        stats = self.download_manager.get_stats()
        logger.success(
            f"下载完成: {stats.completed} 成功, {stats.failed} 失败, {stats.skipped} 跳过"
        )

        # 广播 stats_update
        if self._broadcaster:
            await self._broadcaster(
                {
                    "event": "stats_update",
                    "data": {
                        "total": stats.total,
                        "completed": stats.completed,
                        "failed": stats.failed,
                        "skipped": stats.skipped,
                        "bytes_downloaded": stats.bytes_downloaded,
                    },
                }
            )


# ---------------------------------------------------------------------------
# EventBridgePlugin
# ---------------------------------------------------------------------------


def _safe_str(value: object, default: str = "") -> str:
    """安全转换为字符串"""
    if value is None:
        return default
    return str(value)


def _safe_int(value: object, default: int = 0) -> int:
    """安全转换为整数"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class EventBridgePlugin(ModFetchPlugin):
    """
    事件桥接插件

    注册全部 14 个 HookType 处理器，将 HookContext 转换为 WebSocket 事件字典
    并通过 broadcaster 回调推送到所有订阅者。
    """

    name = "event_bridge"
    version = "1.0.0"
    description = "将插件 Hook 事件桥接到 WebSocket"
    author = "ModFetch Server"

    def __init__(self, broadcaster: EventBroadcaster):
        super().__init__()
        self._broadcaster = broadcaster
        self._resolved_count = 0
        self._failed_count = 0
        self._downloaded_count = 0
        self._bytes_downloaded = 0
        self._total_mods = 0

    def register_hooks(self) -> dict[HookType, Callable]:
        """注册全部 14 个 Hook 处理器"""
        return {
            HookType.CONFIG_LOADED: self._on_config_loaded,
            HookType.CONFIG_VALIDATED: self._on_config_validated,
            HookType.PRE_RESOLVE: self._on_pre_resolve,
            HookType.POST_RESOLVE: self._on_post_resolve,
            HookType.PRE_RESOLVE_DEPENDENCIES: self._on_pre_resolve_deps,
            HookType.POST_RESOLVE_DEPENDENCIES: self._on_post_resolve_deps,
            HookType.PRE_DOWNLOAD: self._on_pre_download,
            HookType.DOWNLOAD_PROGRESS: self._on_download_progress,
            HookType.POST_DOWNLOAD: self._on_post_download,
            HookType.DOWNLOAD_FAILED: self._on_download_failed,
            HookType.PRE_PACKAGE: self._on_pre_package,
            HookType.POST_PACKAGE: self._on_post_package,
            HookType.PLUGIN_LOAD: self._on_plugin_load,
            HookType.PLUGIN_UNLOAD: self._on_plugin_unload,
        }

    # -- 配置阶段 --------------------------------------------------------

    async def _on_config_loaded(self, context: HookContext) -> HookResult:
        """配置加载完成 → phase_change: resolve"""
        self._total_mods = len(context.config.minecraft.mods)
        await self._broadcaster(
            {"event": "phase_change", "data": {"phase": "resolve"}}
        )
        return HookResult()

    async def _on_config_validated(self, context: HookContext) -> HookResult:
        """配置验证完成 → stats_update"""
        await self._broadcast_stats()
        return HookResult()

    # -- 解析阶段 --------------------------------------------------------

    async def _on_pre_resolve(self, context: HookContext) -> HookResult:
        """解析模组前 → resolve_start"""
        mod_slug = self._extract_mod_slug(context)
        mc_version = _safe_str(context.version)
        loader = self._extract_loader(context)
        await self._broadcaster(
            {
                "event": "resolve_start",
                "data": {
                    "mod_slug": mod_slug,
                    "mc_version": mc_version,
                    "loader": loader,
                },
            }
        )
        return HookResult()

    async def _on_post_resolve(self, context: HookContext) -> HookResult:
        """解析模组后 → resolve_complete"""
        self._resolved_count += 1
        mod_slug = self._extract_mod_slug(context)

        title = mod_slug
        version = ""
        dep_count = 0

        project_info = context.extra_data.get("project_info")
        if isinstance(project_info, ProjectInfo):
            title = project_info.title
            mod_slug = project_info.name

        version_info = context.extra_data.get("version_info")
        if isinstance(version_info, VersionInfo):
            version = version_info.version
            dep_count = len(version_info.dependencies)

        await self._broadcaster(
            {
                "event": "resolve_complete",
                "data": {
                    "mod_slug": mod_slug,
                    "title": title,
                    "version": version,
                    "dependencies": dep_count,
                },
            }
        )
        await self._broadcast_stats()
        return HookResult()

    async def _on_pre_resolve_deps(self, context: HookContext) -> HookResult:
        """解析依赖前 — 无对应 WebSocket 事件"""
        return HookResult()

    async def _on_post_resolve_deps(self, context: HookContext) -> HookResult:
        """解析依赖后 → stats_update"""
        deps = context.extra_data.get("dependencies")
        if isinstance(deps, list):
            self._total_mods += len(deps)
        await self._broadcast_stats()
        return HookResult()

    # -- 下载阶段 --------------------------------------------------------

    async def _on_pre_download(self, context: HookContext) -> HookResult:
        """下载开始 → download_start"""
        filename = _safe_str(context.extra_data.get("filename"))
        url = _safe_str(context.extra_data.get("url"))
        await self._broadcaster(
            {
                "event": "download_start",
                "data": {"filename": filename, "size": 0, "url": url},
            }
        )
        return HookResult()

    async def _on_download_progress(self, context: HookContext) -> HookResult:
        """下载进度 → download_progress"""
        filename = _safe_str(context.extra_data.get("filename"))
        percent = _safe_float(context.extra_data.get("percent"))
        await self._broadcaster(
            {
                "event": "download_progress",
                "data": {
                    "filename": filename,
                    "percent": percent,
                    "bytes_downloaded": 0,
                    "bytes_total": 0,
                },
            }
        )
        return HookResult()

    async def _on_post_download(self, context: HookContext) -> HookResult:
        """下载完成 → download_complete"""
        self._downloaded_count += 1
        filename = _safe_str(context.extra_data.get("filename"))
        await self._broadcaster(
            {
                "event": "download_complete",
                "data": {"filename": filename, "size": 0},
            }
        )
        await self._broadcast_stats()
        return HookResult()

    async def _on_download_failed(self, context: HookContext) -> HookResult:
        """下载失败 → download_failed"""
        self._failed_count += 1
        filename = _safe_str(context.extra_data.get("filename"))
        error_msg = _safe_str(context.extra_data.get("error"))
        retries = _safe_int(context.extra_data.get("retries"))
        await self._broadcaster(
            {
                "event": "download_failed",
                "data": {
                    "filename": filename,
                    "error": {"code": "E300", "message": error_msg},
                    "retries": retries,
                },
            }
        )
        await self._broadcast_stats()
        return HookResult()

    # -- 打包阶段 --------------------------------------------------------

    async def _on_pre_package(self, context: HookContext) -> HookResult:
        """打包前 → phase_change: package + package_start"""
        await self._broadcaster(
            {"event": "phase_change", "data": {"phase": "package"}}
        )
        mc_version = _safe_str(context.version)
        fmt = _safe_str(context.extra_data.get("format", "mrpack"))
        await self._broadcaster(
            {
                "event": "package_start",
                "data": {
                    "format": fmt,
                    "mc_version": mc_version,
                    "loader": "",
                    "mode": "",
                },
            }
        )
        return HookResult()

    async def _on_post_package(self, context: HookContext) -> HookResult:
        """打包后 → package_complete"""
        output_path = _safe_str(context.extra_data.get("output_path"))
        fmt = _safe_str(context.extra_data.get("format", "mrpack"))
        filename = os.path.basename(output_path) if output_path else ""
        size = 0
        if output_path and os.path.exists(output_path):
            try:
                size = os.path.getsize(output_path)
            except OSError:
                size = 0

        await self._broadcaster(
            {
                "event": "package_complete",
                "data": {
                    "filename": filename,
                    "path": output_path,
                    "size": size,
                    "format": fmt,
                },
            }
        )
        return HookResult()

    # -- 插件生命周期 ----------------------------------------------------

    async def _on_plugin_load(self, context: HookContext) -> HookResult:
        """插件加载 — 无对应 WebSocket 事件"""
        return HookResult()

    async def _on_plugin_unload(self, context: HookContext) -> HookResult:
        """插件卸载 — 无对应 WebSocket 事件"""
        return HookResult()

    # -- 辅助方法 --------------------------------------------------------

    def _extract_mod_slug(self, context: HookContext) -> str:
        """从 HookContext 中提取模组 slug"""
        if context.mod_entry is not None:
            if context.mod_entry.slug:
                return context.mod_entry.slug
            if context.mod_entry.id:
                return context.mod_entry.id
        return "unknown"

    def _extract_loader(self, context: HookContext) -> str:
        """从配置中提取当前加载器"""
        mod_loader = context.config.minecraft.mod_loader
        if isinstance(mod_loader, list):
            if mod_loader:
                return mod_loader[0].value
            return ""
        return mod_loader.value

    async def _broadcast_stats(self) -> None:
        """广播当前统计信息"""
        await self._broadcaster(
            {
                "event": "stats_update",
                "data": {
                    "total": self._total_mods,
                    "completed": self._downloaded_count,
                    "failed": self._failed_count,
                    "skipped": 0,
                    "bytes_downloaded": self._bytes_downloaded,
                },
            }
        )
