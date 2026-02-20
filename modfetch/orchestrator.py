"""
主协调器

整合所有服务层组件，实现下载流程编排。
"""

import os
from typing import List, Set

from loguru import logger

from modfetch.models import ModFetchConfig, ModEntry, ModLoader
from modfetch.services import (
    ModrinthClient,
    ModResolver,
    DependencyResolver,
    VersionMatcher,
)
from modfetch.download import DownloadManager
from modfetch.packager import MrpackBuilder, ZipBuilder
from modfetch.exceptions import ConfigError, DownloadError


class ModFetchOrchestrator:
    """ModFetch 主协调器"""

    def __init__(self, config: ModFetchConfig):
        self.config = config
        self.client = ModrinthClient()
        self.resolver = ModResolver(self.client)
        self.dep_resolver = DependencyResolver(self.client)
        self.version_matcher = VersionMatcher(self.client)
        self.download_manager: DownloadManager
        self.mrpack_builder = MrpackBuilder()
        self.zip_builder = ZipBuilder()

        self._processed_mods: Set[str] = set()
        self._skipped_mods: List[str] = []

    async def run(self):
        """运行完整的下载流程"""
        logger.info("开始 ModFetch 下载任务...")

        try:
            self._validate_config()

            # 处理每个 Minecraft 版本
            for version in self.config.minecraft.version:
                logger.info(f"处理 Minecraft {version}...")
                await self._process_version(version)

            # 生成输出
            await self._generate_outputs()

            logger.success("ModFetch 任务完成!")

        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            raise
        finally:
            await self.client.close()

    def _validate_config(self):
        """验证配置"""
        if not self.config.minecraft.version:
            raise ConfigError("请配置 Minecraft 版本")

        if not self.config.minecraft.mods:
            raise ConfigError("请配置至少一个模组")

        if self.config.minecraft.mod_loader not in [
            ModLoader.FORGE,
            ModLoader.FABRIC,
            ModLoader.QUILT,
        ]:
            raise ConfigError("mod_loader 必须为 forge/fabric/quilt")

    async def _process_version(self, version: str):
        """处理单个版本"""
        logger.info(
            f"准备下载目录 for {version}-{self.config.minecraft.mod_loader.value}"
        )

        # 设置下载目录
        version_dir = os.path.join(
            self.config.output.download_dir,
            f"{version}-{self.config.minecraft.mod_loader.value}",
        )
        os.makedirs(version_dir, exist_ok=True)
        logger.success(f"目录设定成功: {version_dir}")

        # 创建下载管理器
        self.download_manager = DownloadManager(
            max_concurrent=self.config.max_concurrent,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            progress_callback=self._on_download_progress,
        )

        # 处理模组
        await self._process_mods(version, version_dir)

        # 处理资源包
        await self._process_resourcepacks(version, version_dir)

        # 处理光影包
        await self._process_shaderpacks(version, version_dir)

        # 处理额外 URL
        await self._process_extra_urls(version, version_dir)

        # 执行下载
        logger.info(f"启动下载 ({self.config.max_concurrent}并发)...")
        await self.download_manager.run()

        stats = self.download_manager.get_stats()
        logger.success(
            f"下载完成: {stats.completed} 成功, {stats.failed} 失败, {stats.skipped} 跳过"
        )

    async def _process_mods(self, version: str, version_dir: str):
        """处理模组"""
        logger.info(f"开始处理 {len(self.config.minecraft.mods)} 个模组...")

        for mod in self.config.minecraft.mods:
            if not self._should_include(mod, version):
                logger.debug(f"模组 {mod} 被过滤，不适用于当前版本或功能")
                continue

            # 解析模组
            result = await self.resolver.resolve(
                mod, version, self.config.minecraft.mod_loader.value
            )

            if not result:
                self._skipped_mods.append(str(mod))
                logger.warning(f"无法解析模组: {mod}")
                continue

            project_info, version_info, file_info = result

            if project_info.id in self._processed_mods:
                logger.debug(f"模组 {project_info.name} 已处理，跳过")
                continue

            self._processed_mods.add(project_info.id)
            logger.info(f"正在分析模组 '{project_info.name}' (ID: {project_info.id})")

            # 添加到下载队列
            await self.download_manager.enqueue(
                url=file_info["url"],
                filename=file_info["filename"],
                download_dir=os.path.join(version_dir, "mods"),
                sha1=file_info.get("hashes", {}).get("sha1"),
                category="mods",
            )
            logger.success(f"模组 '{project_info.name}' 已加入下载队列")

            # 处理依赖
            await self._process_dependencies(version_info, version, version_dir)

    async def _process_dependencies(self, version_info, version: str, version_dir: str):
        """处理依赖"""
        deps = await self.dep_resolver.resolve(
            version_info, version, self.config.minecraft.mod_loader.value
        )

        if deps:
            logger.info(f"发现 {len(deps)} 个依赖需要处理")

        for dep_info, dep_version, dep_file in deps:
            if dep_info.id in self._processed_mods:
                continue

            self._processed_mods.add(dep_info.id)
            logger.info(f"添加依赖: {dep_info.name} (ID: {dep_info.id})")

            await self.download_manager.enqueue(
                url=dep_file["url"],
                filename=dep_file["filename"],
                download_dir=os.path.join(version_dir, "mods"),
                sha1=dep_file.get("hashes", {}).get("sha1"),
                category="mods",
            )

    async def _process_resourcepacks(self, version: str, version_dir: str):
        """处理资源包"""
        if not self.config.minecraft.resourcepacks:
            return

        logger.info(f"开始处理 {len(self.config.minecraft.resourcepacks)} 个资源包...")

        for pack in self.config.minecraft.resourcepacks:
            if not self._should_include(pack, version):
                continue

            result = await self.resolver.resolve(
                pack, version, self.config.minecraft.mod_loader.value
            )

            if not result:
                logger.warning(f"无法解析资源包: {pack}")
                continue

            project_info, version_info, file_info = result

            await self.download_manager.enqueue(
                url=file_info["url"],
                filename=file_info["filename"],
                download_dir=os.path.join(version_dir, "resourcepacks"),
                sha1=file_info.get("hashes", {}).get("sha1"),
                category="resourcepacks",
            )
            logger.success(f"资源包 '{project_info.name}' 已加入下载队列")

    async def _process_shaderpacks(self, version: str, version_dir: str):
        """处理光影包"""
        if not self.config.minecraft.shaderpacks:
            return

        logger.info(f"开始处理 {len(self.config.minecraft.shaderpacks)} 个光影包...")

        for pack in self.config.minecraft.shaderpacks:
            if not self._should_include(pack, version):
                continue

            result = await self.resolver.resolve(
                pack, version, self.config.minecraft.mod_loader.value
            )

            if not result:
                logger.warning(f"无法解析光影包: {pack}")
                continue

            project_info, version_info, file_info = result

            await self.download_manager.enqueue(
                url=file_info["url"],
                filename=file_info["filename"],
                download_dir=os.path.join(version_dir, "shaderpacks"),
                sha1=file_info.get("hashes", {}).get("sha1"),
                category="shaderpacks",
            )
            logger.success(f"光影包 '{project_info.name}' 已加入下载队列")

    async def _process_extra_urls(self, version: str, version_dir: str):
        """处理额外 URL"""
        if not self.config.minecraft.extra_urls:
            return

        logger.info(f"开始处理 {len(self.config.minecraft.extra_urls)} 个额外 URL...")

        for extra in self.config.minecraft.extra_urls:
            if not self._should_include(extra, version):
                logger.debug(f"额外 URL {extra.url} 被过滤")
                continue

            category = extra.type.value.replace("pack", "packs")

            await self.download_manager.enqueue(
                url=extra.url,
                filename=extra.filename or extra.url.split("/")[-1],
                download_dir=os.path.join(version_dir, category),
                sha1=extra.sha1,
                category=category,
            )
            logger.success(f"额外 URL '{extra.filename}' 已加入下载队列")

    def _should_include(self, entry, version: str) -> bool:
        """检查是否应该包含该项"""
        features = self.config.features
        return self.version_matcher.should_include(entry, version, features)

    async def _generate_outputs(self):
        """生成输出文件"""
        output_formats = self.config.output.format

        if "mrpack" in output_formats:
            await self._generate_mrpacks()

        if "zip" in output_formats:
            await self._generate_zips()

    async def _generate_mrpacks(self):
        """生成 mrpack 文件"""
        logger.info("开始生成 mrpack 整合包...")

        metadata = {
            "name": self.config.metadata.name,
            "version": self.config.metadata.version,
            "description": self.config.metadata.description,
        }

        for version in self.config.minecraft.version:
            source_dir = os.path.join(
                self.config.output.download_dir,
                f"{version}-{self.config.minecraft.mod_loader.value}",
            )

            if not os.path.exists(source_dir):
                logger.warning(f"源目录不存在: {source_dir}")
                continue

            output_name = f"{metadata['name']}_{metadata['version']}_MC{version}-{self.config.minecraft.mod_loader.value}"
            output_path = os.path.join(self.config.output.download_dir, output_name)

            loader_version = await self.version_matcher.get_loader_version(
                self.config.minecraft.mod_loader, version
            )

            try:
                mrpack_path = await self.mrpack_builder.build(
                    source_dir=source_dir,
                    output_path=output_path,
                    metadata=metadata,
                    mc_version=version,
                    mod_loader=self.config.minecraft.mod_loader,
                    loader_version=loader_version,
                )
                logger.success(f"mrpack 生成成功: {mrpack_path}")
            except Exception as e:
                logger.error(f"mrpack 生成失败: {e}")

    async def _generate_zips(self):
        """生成 ZIP 文件"""
        logger.info("开始生成 ZIP 归档...")

        for version in self.config.minecraft.version:
            source_dir = os.path.join(
                self.config.output.download_dir,
                f"{version}-{self.config.minecraft.mod_loader.value}",
            )

            if not os.path.exists(source_dir):
                logger.warning(f"源目录不存在: {source_dir}")
                continue

            try:
                zip_path = await self.zip_builder.build(
                    source_dir=source_dir,
                    output_path=self.config.output.download_dir,
                    archive_name=f"archive-{version}-{self.config.minecraft.mod_loader.value}",
                )
                logger.success(f"ZIP 生成成功: {zip_path}")
            except Exception as e:
                logger.error(f"ZIP 生成失败: {e}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "processed_mods": len(self._processed_mods),
            "skipped": self._skipped_mods,
        }
