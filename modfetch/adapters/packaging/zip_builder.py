"""
ZIP 构建器（自 packager.zip 迁移）

实现目录压缩功能。

压缩操作（``shutil.make_archive``）为 CPU + 同步 IO 密集，移入
``asyncio.to_thread`` 在事件循环外执行，避免阻塞 Web 端其他并发任务。
"""

import asyncio
import os
import shutil
from typing import Optional

from modfetch.domain.errors import ZipError


class ZipBuilder:
    """ZIP 构建器

    将目录压缩为 .zip 归档（archive_name 缺省取目录名）。
    """

    async def build(
        self,
        source_dir: str,
        output_path: str,
        archive_name: Optional[str] = None,
    ) -> str:
        """
        构建 ZIP 文件

        在 output_path 下生成 {archive_name}.zip，归档根为 source_dir
        的内容（不含 source_dir 自身目录层级）。

        Args:
            source_dir: 源文件目录（归档根内容）
            output_path: 输出目录
            archive_name: 压缩包名称（不含扩展名）；缺省取 source_dir 目录名

        Returns:
            生成的文件完整路径（{output_path}/{archive_name}.zip）

        Raises:
            ZipError: 压缩失败（如源目录不存在或无权限）
        """
        try:
            if archive_name is None:
                archive_name = os.path.basename(source_dir)
            zip_path = os.path.join(output_path, archive_name)

            # 压缩为同步 IO，移入 worker 线程避免阻塞事件循环
            return await asyncio.to_thread(
                self._zip_sync, zip_path, source_dir
            )
        except Exception as e:
            # 统一包装为 ZipError，附带上下文供调用方定位
            raise ZipError(
                f"构建 ZIP 失败: {e}",
                context={"source_dir": source_dir, "output_path": output_path},
            )

    def _zip_sync(self, zip_path: str, source_dir: str) -> str:
        """同步压缩（worker 线程内执行）

        shutil.make_archive 自动追加 .zip 后缀。
        """
        shutil.make_archive(zip_path, "zip", source_dir)
        return f"{zip_path}.zip"

    async def build_multi_version(
        self,
        base_dir: str,
        versions: list[str],
        mod_loader: str,
        output_dir: Optional[str] = None,
    ) -> list[str]:
        """为多个版本构建 ZIP（保留旧接口）

        版本目录命名约定 {mc版本}-{加载器}，归档名固定为
        archive-{mc版本}-{加载器}；单版本失败不中断整体。
        """
        if output_dir is None:
            output_dir = base_dir

        results = []
        for version in versions:
            # 按 {version}-{loader} 命名约定定位该版本的源目录
            source_dir = os.path.join(base_dir, f"{version}-{mod_loader}")
            if not os.path.exists(source_dir):
                # 该版本目录缺失则跳过
                continue

            # 归档命名约定: archive-{mc版本}-{加载器}
            archive_name = f"archive-{version}-{mod_loader}"

            try:
                zip_path = await self.build(
                    source_dir=source_dir,
                    output_path=output_dir,
                    archive_name=archive_name,
                )
                results.append(zip_path)
            except ZipError:
                # 单版本失败不中断整体构建，跳过继续
                pass

        return results