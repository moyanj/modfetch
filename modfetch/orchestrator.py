"""
主协调器（过渡形态）

编排职责已迁移:
- 解析/展开 → application.plan_build.PlanBuild（产出 BuildPlan）
- 本类仅保留: 插件 Hook 桥接、按 plan 驱动下载与打包、统计

将随 BuildApplicationService（阶段 8）落地而退役。
"""

import os
import shutil
import tempfile
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

from modfetch.application.plan_build import PlanBuild, PlanReport
from modfetch.domain.build_plan import (
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.models import (
    ModFetchConfig,
    ModLoader,
    MrpackMode,
    OutputFormat,
)
from modfetch.services import (
    ModrinthClient,
    VersionMatcher,
)
from modfetch.download import DownloadManager
from modfetch.packager import MrpackBuilder, ZipBuilder
from modfetch.exceptions import ConfigError
from modfetch.plugins import PluginManager, HookType, HookContext


#: PlanBuild 事件名 → 插件 HookType 映射
_PLAN_HOOK_MAP = {
    "pre_resolve": HookType.PRE_RESOLVE,
    "post_resolve": HookType.POST_RESOLVE,
    "pre_resolve_dependencies": HookType.PRE_RESOLVE_DEPENDENCIES,
    "post_resolve_dependencies": HookType.POST_RESOLVE_DEPENDENCIES,
}


class ModFetchOrchestrator:
    """ModFetch 主协调器"""

    def __init__(
        self, config: ModFetchConfig, plugin_manager: Optional[PluginManager] = None
    ):
        self.config = config
        self.client = ModrinthClient()
        self.version_matcher = VersionMatcher(self.client)
        self.download_manager: DownloadManager
        self.mrpack_builder = MrpackBuilder()
        self.zip_builder = ZipBuilder()
        self.plugin_manager = plugin_manager or PluginManager()

        self._plan: Optional[BuildPlan] = None
        self._plan_report: Optional[PlanReport] = None
        self._processed_by_target: Dict[BuildTarget, Set[str]] = {}
        self._skipped_by_target: Dict[BuildTarget, List[str]] = {}
        self._last_target: Optional[BuildTarget] = None

    def _on_download_progress(self, filename: str, percent: float):
        """下载进度回调"""
        pass

    async def run(self):
        """运行完整的下载流程"""
        logger.info("开始 ModFetch 下载任务...")

        try:
            # Hook: 配置加载完成
            await self._execute_hook(HookType.CONFIG_LOADED)

            self._validate_config()

            # Hook: 配置验证完成
            await self._execute_hook(HookType.CONFIG_VALIDATED)

            # 生成构建计划（解析全部 target 的模组/依赖/资源）
            plan_builder = PlanBuild(
                self.client,
                version_matcher=self.version_matcher,
                hook=self._plan_hook,
            )
            self._plan, self._plan_report = await plan_builder.execute(
                self.config, self.config.features
            )

            # 记录每个 target 的处理/跳过统计（保持旧 get_stats 语义）
            for target in self._plan.targets:
                self._processed_by_target[target] = {
                    a.project_id
                    for a in self._plan.artifacts_for(target)
                    if a.category.value == "mods" and a.origin == "catalog"
                }
                self._skipped_by_target[target] = list(
                    self._plan_report.skipped_by_target.get(target, ())
                )

            # 逐 target 下载 + 打包
            for target in self._plan.targets:
                logger.info(
                    f"处理 Minecraft {target.minecraft_version} "
                    f"({target.loader.value})..."
                )
                self._last_target = target
                await self._process_version(target.minecraft_version, target.loader)

            logger.success("ModFetch 任务完成!")

        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            raise
        finally:
            await self.client.close()

    async def _plan_hook(self, name: str, **kwargs) -> None:
        """PlanBuild 事件 → 插件 Hook 桥接"""
        hook_type = _PLAN_HOOK_MAP.get(name)
        if hook_type is not None:
            await self._execute_hook(hook_type, **kwargs)

    async def _execute_hook(self, hook_type: HookType, **kwargs) -> None:
        """执行指定类型的 Hook"""
        context = HookContext(
            config=self.config,
            version=kwargs.get("version"),
            mod_entry=kwargs.get("mod_entry"),
            download_info=kwargs.get("download_info"),
            extra_data=kwargs.get("extra_data", {}),
        )
        await self.plugin_manager.execute_hook(hook_type, context)

    def _validate_config(self):
        """验证配置（委托给 ModFetchConfig.validate）"""
        try:
            self.config.validate()
        except ValueError as e:
            raise ConfigError(str(e)) from e

    @staticmethod
    def _build_mrpack_entry(
        subdir: str, file_info: dict, env: Optional[dict[str, str]] = None
    ) -> dict:
        """构建 mrpack 文件条目

        Args:
            subdir: 子目录名 (mods/resourcepacks/shaderpacks)
            file_info: 文件信息字典
            env: 环境标记，默认 {"client": "required", "server": "required"}
        """
        return {
            "path": f"{subdir}/{file_info['filename']}",
            "hashes": file_info.get("hashes", {}),
            "env": env or {"client": "required", "server": "required"},
            "downloads": [file_info["url"]],
            "fileSize": file_info.get("size", 0),
        }

    @property
    def _needs_download(self) -> bool:
        """是否需要下载文件"""
        return (
            MrpackMode.DOWNLOAD in self.config.output.mrpack_modes
            or OutputFormat.ZIP in self.config.output.format
        )

    # -- 下载阶段 -----------------------------------------------------------

    def _find_target(self, version: str, loader: ModLoader) -> BuildTarget:
        """定位当前处理的 BuildTarget"""
        assert self._plan is not None
        for target in self._plan.targets:
            if target.minecraft_version == version and target.loader == loader:
                return target
        raise KeyError(f"BuildTarget 不存在: {version}/{loader.value}")

    def _version_dir(self, target: BuildTarget) -> str:
        return os.path.join(self.config.output.download_dir, target.dir_name)

    def _create_download_manager(self) -> DownloadManager:
        """创建下载管理器（子类可替换为事件感知实现）"""
        return DownloadManager(
            max_concurrent=self.config.max_concurrent,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            progress_callback=self._on_download_progress,
        )

    async def _before_download(self, target: BuildTarget) -> None:
        """下载开始前钩子（子类可广播事件）"""

    async def _after_download(self, target: BuildTarget, stats) -> None:
        """下载完成后钩子（子类可广播事件）"""

    async def _process_version(self, version: str, loader: ModLoader):
        """处理单个 (版本, 加载器) 组合：入队 plan 制品并执行下载"""
        target = self._find_target(version, loader)
        logger.info(f"准备下载目录 for {target.dir_name}")

        version_dir = self._version_dir(target)
        os.makedirs(version_dir, exist_ok=True)
        logger.success(f"目录设定成功: {version_dir}")

        self.download_manager = self._create_download_manager()

        # 按 plan 入队下载任务
        for artifact in self._plan.artifacts_for(target):
            if artifact.origin == "catalog" and not self._needs_download:
                logger.info(f"'{artifact.project_name}' 已记录引用 (跳过下载)")
                continue
            await self._enqueue_artifact(artifact, version_dir)

        await self._before_download(target)

        # 执行下载
        logger.info(f"启动下载 ({self.config.max_concurrent}并发)...")
        await self.download_manager.run()

        stats = self.download_manager.get_stats()
        logger.success(
            f"下载完成: {stats.completed} 成功, {stats.failed} 失败, "
            f"{stats.skipped} 跳过"
        )

        await self._after_download(target, stats)

        # 生成该 target 的输出
        await self._generate_outputs_for_version(version, loader)

    async def _enqueue_artifact(
        self, artifact: ResolvedArtifact, version_dir: str
    ) -> None:
        """将制品加入下载队列"""
        download_dir = os.path.join(
            version_dir, os.path.dirname(artifact.destination)
        )
        await self.download_manager.enqueue(
            url=artifact.url,
            filename=artifact.filename,
            download_dir=download_dir,
            sha1=artifact.hashes.get("sha1"),
            category=artifact.category.value,
        )
        logger.success(f"'{artifact.project_name}' 已加入下载队列")

    # -- 打包阶段 -----------------------------------------------------------

    def _mrpack_files_for(self, target: BuildTarget) -> List[dict]:
        """REFERENCE 模式 manifest 文件列表（仅平台解析的制品）"""
        assert self._plan is not None
        return [
            artifact.to_mrpack_entry()
            for artifact in self._plan.artifacts_for(target)
            if artifact.origin == "catalog"
        ]

    def _extra_url_destinations(self, target: BuildTarget) -> List[str]:
        """extra_urls 的目标路径（REFERENCE 模式下仍纳入 overrides）"""
        assert self._plan is not None
        version_dir = self._version_dir(target)
        return [
            os.path.join(version_dir, artifact.destination)
            for artifact in self._plan.artifacts_for(target)
            if artifact.origin == "extra_url"
        ]

    async def _generate_outputs_for_version(self, version: str, loader: ModLoader):
        """为特定版本和加载器生成输出文件"""
        assert self._plan is not None
        target = self._find_target(version, loader)
        for spec in self._plan.outputs_for(target):
            if spec.format == "mrpack":
                await self._generate_mrpack(target, spec)
            elif spec.format == "zip":
                await self._generate_zip(target, spec)

    async def _generate_mrpack(self, target: BuildTarget, spec: OutputSpec):
        """生成 mrpack 文件"""
        version = target.minecraft_version
        loader = target.loader
        mode = MrpackMode(spec.mrpack_mode)

        # Hook: 打包前
        await self._execute_hook(HookType.PRE_PACKAGE, version=version)

        metadata = {
            "name": self.config.metadata.name,
            "version": self.config.metadata.version,
            "description": self.config.metadata.description,
        }

        source_dir = self._version_dir(target)
        os.makedirs(source_dir, exist_ok=True)

        loader_version = await self.version_matcher.get_loader_version(
            loader, version
        )

        logger.info(
            f"正在生成 Minecraft {version} ({loader.value}) 的 "
            f"mrpack ({mode.value} 模式)..."
        )
        output_path = os.path.join(
            self.config.output.download_dir, spec.output_name
        )

        # 在 REFERENCE 模式下，source_dir 内容不应进入 overrides
        # 但 extra_urls 的本地文件仍需要进入 overrides
        if mode == MrpackMode.DOWNLOAD:
            actual_source = source_dir
        else:
            actual_source = os.path.join(source_dir, "non_existent_empty_dir")
            os.makedirs(actual_source, exist_ok=True)

            destinations = self._extra_url_destinations(target)
            if destinations:
                extra_source = tempfile.mkdtemp(
                    prefix="modfetch_extra_overrides_"
                )
                for dest in destinations:
                    if os.path.exists(dest):
                        rel_path = os.path.relpath(dest, source_dir)
                        override_dest = os.path.join(extra_source, rel_path)
                        if os.path.isdir(dest):
                            shutil.copytree(
                                dest, override_dest, dirs_exist_ok=True
                            )
                        else:
                            os.makedirs(
                                os.path.dirname(override_dest) or extra_source,
                                exist_ok=True,
                            )
                            shutil.copy2(dest, override_dest)
                actual_source = extra_source

        try:
            mrpack_path = await self.mrpack_builder.build(
                source_dir=actual_source,
                output_path=output_path,
                metadata=metadata,
                mc_version=version,
                mod_loader=loader,
                loader_version=loader_version,
                files=(
                    self._mrpack_files_for(target)
                    if mode == MrpackMode.REFERENCE
                    else None
                ),
            )
            logger.success(f"mrpack ({mode.value}) 生成成功: {mrpack_path}")

            # Hook: 打包后
            await self._execute_hook(
                HookType.POST_PACKAGE,
                version=version,
                extra_data={"output_path": mrpack_path, "format": "mrpack"},
            )
        except Exception as e:
            logger.error(f"mrpack ({mode.value}) 生成失败: {e}")
        finally:
            if mode == MrpackMode.REFERENCE and os.path.exists(actual_source):
                shutil.rmtree(actual_source)

    async def _generate_zip(self, target: BuildTarget, spec: OutputSpec):
        """生成 ZIP 文件"""
        version = target.minecraft_version
        logger.info(
            f"开始生成 Minecraft {version} ({target.loader.value}) 的 ZIP 归档..."
        )

        source_dir = self._version_dir(target)
        if not os.path.exists(source_dir):
            logger.warning(f"源目录不存在: {source_dir}")
            return

        try:
            zip_path = await self.zip_builder.build(
                source_dir=source_dir,
                output_path=self.config.output.download_dir,
                archive_name=spec.output_name,
            )
            logger.success(f"ZIP 生成成功: {zip_path}")

            # Hook: 打包后
            await self._execute_hook(
                HookType.POST_PACKAGE,
                version=version,
                extra_data={"output_path": zip_path, "format": "zip"},
            )
        except Exception as e:
            logger.error(f"ZIP 生成失败: {e}")

    # -- 统计 ----------------------------------------------------------------

    def get_stats(self) -> dict:
        """获取统计信息（保持旧语义: 最后一个 target 的处理/跳过）"""
        if self._last_target is None:
            return {"processed_mods": 0, "skipped": []}
        return {
            "processed_mods": len(
                self._processed_by_target.get(self._last_target, set())
            ),
            "skipped": self._skipped_by_target.get(self._last_target, []),
        }
