"""
Mrpack 生成器

实现 Modrinth 标准整合包 (.mrpack) 的生成。
"""

import json
import os
import shutil
from typing import Optional

import aiofiles

from modfetch.models import ModLoader
from modfetch.exceptions import MrpackError


class MrpackBuilder:
    """Mrpack 构建器"""

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
            # 创建临时目录
            temp_dir = f"{output_path}_temp"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            # 创建 overrides 目录
            overrides_dir = os.path.join(temp_dir, "overrides")
            os.makedirs(overrides_dir, exist_ok=True)

            # 生成 manifest
            manifest = self._create_manifest(
                metadata, mc_version, mod_loader, loader_version
            )

            if files:
                manifest["files"] = files

            # 写入 manifest.json
            manifest_path = os.path.join(temp_dir, "modrinth.index.json")
            async with aiofiles.open(manifest_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(manifest, indent=4))

            # 复制文件到 overrides
            if os.path.exists(source_dir) and any(os.listdir(source_dir)):
                await self._copy_to_overrides(source_dir, overrides_dir)

            # 创建 zip 文件
            zip_path = f"{output_path}.zip"
            shutil.make_archive(output_path, "zip", temp_dir)

            # 重命名为 .mrpack
            mrpack_path = f"{output_path}.mrpack"
            if os.path.exists(mrpack_path):
                os.remove(mrpack_path)
            shutil.move(zip_path, mrpack_path)

            # 清理临时目录
            shutil.rmtree(temp_dir)

            return mrpack_path

        except Exception as e:
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
        """创建 manifest.json"""
        mod_loader_id = mod_loader.value.lower()

        dependencies = {"minecraft": mc_version}
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
        """复制文件到 overrides 目录"""
        for root, dirs, files in os.walk(source_dir):
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
        """
        为多个版本构建 mrpack

        Args:
            base_dir: 基础目录
            versions: 版本列表
            metadata: 包元数据
            mod_loader: 模组加载器
            get_loader_version_fn: 获取加载器版本的函数

        Returns:
            生成的文件路径列表
        """
        results = []
        for version in versions:
            source_dir = os.path.join(base_dir, f"{version}-{mod_loader.value}")
            if not os.path.exists(source_dir):
                continue

            output_name = f"{metadata.get('name', 'pack')}_{metadata.get('version', '1.0.0')}_MC{version}-{mod_loader.value}"
            output_path = os.path.join(base_dir, output_name)

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
                # 继续处理其他版本
                pass

        return results
