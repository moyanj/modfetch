"""
Mrpack 构建器（自 packager.mrpack 迁移）

实现 Modrinth 标准整合包 (.mrpack) 的生成。
"""

import json
import os
import shutil
from typing import Optional

import aiofiles

from modfetch.domain.config_models import ModLoader
from modfetch.domain.errors import MrpackError


class MrpackBuilder:
    """Mrpack 构建器

    按 Modrinth 标准生成 .mrpack 整合包：
    - 在临时目录组织 modrinth.index.json + overrides/ 布局
    - 压缩为 zip 后重命名为 .mrpack
    """

    async def build(
        self,
        source_dir: str,
        output_path: str,
        metadata: dict,
        mc_version: str,
        mod_loader: ModLoader,
        loader_version: Optional[str] = None,
        files: Optional[list[dict]] = None,
    ) -> str:
        """
        构建 mrpack 文件

        Args:
            source_dir: 源文件目录
            output_path: 输出文件路径（不含扩展名）
            metadata: 包元数据（name, version, description）
            mc_version: Minecraft 版本
            mod_loader: 模组加载器
            loader_version: 加载器版本
            files: 直接写入 manifest 的文件列表（REFERENCE 模式）

        Returns:
            生成的文件路径
        """
        try:
            # 创建临时目录（先清理残留，保证每次构建从干净状态开始）
            temp_dir = f"{output_path}_temp"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            # 创建 overrides 目录：存放直接覆盖游戏目录的文件
            # （config/、mods/ 下的静态文件），不参与 manifest 文件引用
            overrides_dir = os.path.join(temp_dir, "overrides")
            os.makedirs(overrides_dir, exist_ok=True)

            # 生成 manifest（modrinth.index.json 内容）
            manifest = self._create_manifest(
                metadata, mc_version, mod_loader, loader_version
            )

            if files:
                # REFERENCE 模式：文件仅以引用写入 manifest.files，不物理复制
                manifest["files"] = files

            # 写入 manifest.json（mrpack 规范要求的根级索引文件）
            manifest_path = os.path.join(temp_dir, "modrinth.index.json")
            async with aiofiles.open(manifest_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(manifest, indent=4))

            # 复制文件到 overrides（DOWNLOAD 模式：模组/资源文件物理落盘于此）
            if os.path.exists(source_dir) and any(os.listdir(source_dir)):
                await self._copy_to_overrides(source_dir, overrides_dir)

            # 创建 zip 文件（以临时目录为归档根，避免多余的外层目录）
            zip_path = f"{output_path}.zip"
            shutil.make_archive(output_path, "zip", temp_dir)

            # 重命名为 .mrpack（mrpack 本质是含 modrinth.index.json 的 zip）
            mrpack_path = f"{output_path}.mrpack"
            if os.path.exists(mrpack_path):
                os.remove(mrpack_path)
            shutil.move(zip_path, mrpack_path)

            # 清理临时目录
            shutil.rmtree(temp_dir)

            return mrpack_path

        except Exception as e:
            # 统一包装为 MrpackError，附带上下文供调用方定位
            raise MrpackError(
                f"构建 mrpack 失败: {e}",
                context={"source_dir": source_dir, "output_path": output_path},
            )

    def _create_manifest(
        self,
        metadata: dict,
        mc_version: str,
        mod_loader: ModLoader,
        loader_version: Optional[str],
    ) -> dict:
        """创建 manifest.json

        按 mrpack 规范（formatVersion=1）构造 modrinth.index.json：
        - dependencies.minecraft 必填（MC 版本）
        - {loader}-loader 依赖仅在加载器版本已知（非 unknown）时声明
        - files 默认空列表，REFERENCE 模式由调用方填充
        """
        mod_loader_id = mod_loader.value.lower()

        # 依赖声明：minecraft 必填；加载器版本未解析出时不写入 loader 依赖
        dependencies: dict = {"minecraft": mc_version}
        if loader_version and loader_version != "unknown":
            dependencies[f"{mod_loader_id}-loader"] = loader_version

        return {
            "game": "minecraft",
            "formatVersion": 1,
            "versionId": metadata.get("version", "1.0.0"),
            "name": metadata.get("name", "ModFetch Pack"),
            "summary": metadata.get("description", ""),
            "files": [],
            "dependencies": dependencies,
        }

    async def _copy_to_overrides(self, source_dir: str, overrides_dir: str):
        """复制文件到 overrides 目录

        保持 source_dir 的目录结构映射到 overrides/ 下（逐层建目录、
        逐个文件 copy2）。
        """
        for root, dirs, files in os.walk(source_dir):
            # 相对路径决定在 overrides 下的落点（根目录即 overrides/）
            relative_path = os.path.relpath(root, source_dir)
            dest_dir = os.path.join(overrides_dir, relative_path)
            os.makedirs(dest_dir, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                shutil.copy2(src_file, dest_file)

    async def build_multi_version(
        self,
        base_dir: str,
        versions: list[str],
        metadata: dict,
        mod_loader: ModLoader,
        get_loader_version_fn,
    ) -> list[str]:
        """为多个版本构建 mrpack（保留旧接口）

        约定版本目录名为 {mc版本}-{加载器}（如 1.21.1-fabric）；
        单版本构建失败不影响其他版本（结果仅含成功项）。
        """
        results = []
        for version in versions:
            # 按 {version}-{loader} 命名约定定位该版本的源目录
            source_dir = os.path.join(base_dir, f"{version}-{mod_loader.value}")
            if not os.path.exists(source_dir):
                # 该版本目录缺失则跳过
                continue

            # 输出命名: {包名}_{包版本}_MC{MC版本}-{加载器}
            output_name = (
                f"{metadata.get('name', 'pack')}_"
                f"{metadata.get('version', '1.0.0')}_"
                f"MC{version}-{mod_loader.value}"
            )
            output_path = os.path.join(base_dir, output_name)

            # 动态解析该版本的加载器版本（供 manifest 依赖声明）
            loader_version = await get_loader_version_fn(version)

            try:
                mrpack_path = await self.build(
                    source_dir=source_dir,
                    output_path=output_path,
                    metadata=metadata,
                    mc_version=version,
                    mod_loader=mod_loader,
                    loader_version=loader_version,
                )
                results.append(mrpack_path)
            except MrpackError:
                # 单版本失败不中断整体构建，跳过继续
                pass

        return results