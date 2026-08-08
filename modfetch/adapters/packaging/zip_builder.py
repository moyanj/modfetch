"""
ZIP 构建器（自 packager.zip 迁移）

实现目录压缩功能。
"""

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

            # 创建压缩文件（shutil.make_archive 自动追加 .zip 后缀）
            shutil.make_archive(zip_path, "zip", source_dir)

            return f"{zip_path}.zip"

        except Exception as e:
            # 统一包装为 ZipError，附带上下文供调用方定位
            raise ZipError(
                f"构建 ZIP 失败: {e}",
                context={"source_dir": source_dir, "output_path": output_path},
            )