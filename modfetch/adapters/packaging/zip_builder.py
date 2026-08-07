"""
ZIP 构建器（自 packager.zip 迁移）

实现目录压缩功能。
"""

import os
import shutil
from typing import Optional

from modfetch.domain.errors import ZipError


class ZipBuilder:
    """ZIP 构建器"""

    async def build(
        self,
        source_dir: str,
        output_path: str,
        archive_name: Optional[str] = None,
    ) -> str:
        """
        构建 ZIP 文件

        Args:
            source_dir: 源文件目录
            output_path: 输出目录
            archive_name: 压缩包名称（不含扩展名）

        Returns:
            生成的文件路径
        """
        try:
            if archive_name is None:
                archive_name = os.path.basename(source_dir)

            zip_path = os.path.join(output_path, archive_name)

            # 创建压缩文件
            shutil.make_archive(zip_path, "zip", source_dir)

            return f"{zip_path}.zip"

        except Exception as e:
            raise ZipError(
                f"构建 ZIP 失败: {e}",
                context={"source_dir": source_dir, "output_path": output_path},
            )

    async def build_multi_version(
        self,
        base_dir: str,
        versions: list[str],
        mod_loader: str,
        output_dir: Optional[str] = None,
    ) -> list[str]:
        """为多个版本构建 ZIP（保留旧接口）"""
        if output_dir is None:
            output_dir = base_dir

        results = []
        for version in versions:
            source_dir = os.path.join(base_dir, f"{version}-{mod_loader}")
            if not os.path.exists(source_dir):
                continue

            archive_name = f"archive-{version}-{mod_loader}"

            try:
                zip_path = await self.build(
                    source_dir=source_dir,
                    output_path=output_dir,
                    archive_name=archive_name,
                )
                results.append(zip_path)
            except ZipError:
                # 继续处理其他版本
                pass

        return results