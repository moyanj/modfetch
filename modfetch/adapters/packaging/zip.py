"""ZIP 打包器（PackagerPort 实现）

显式接收 source_dir（工作区）与 output_path（最终产物路径）；
产物临时名生成后 atomic_replace 到最终路径，避免半 zip 出现在 dist/。
"""

import os
import uuid
from pathlib import Path

from modfetch.domain.build_plan import (
    BuildPlan,
    OutputArtifact,
    OutputSpec,
)
from modfetch.adapters.packaging.atomicio import AtomicWriteError, atomic_replace
from modfetch.adapters.packaging.zip_builder import ZipBuilder
from modfetch.domain.errors import PackagerError


class ZipPackager:
    """ZIP 打包器（实现 PackagerPort）

    将单个构建目标工作区（source_dir）压缩为 .zip 归档，产物写入
    output_path（含 .zip 扩展名）。
    """

    def __init__(self):
        self._builder = ZipBuilder()

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        source_dir: Path,
        output_path: Path,
    ) -> OutputArtifact:
        """按 OutputSpec 打包单个 target 为 .zip

        Args:
            plan: 构建计划
            spec: 输出规格（format=zip）
            source_dir: target 打包工作区根目录（须已存在）
            output_path: 最终产物路径（含 .zip 扩展名）

        Raises:
            PackagerError: 格式不支持 / 源目录缺失 / 压缩失败
        """
        if spec.format != "zip":
            raise PackagerError(f"ZipPackager 不支持格式: {spec.format}")

        if not source_dir.exists():
            raise PackagerError(
                f"源目录不存在: {source_dir}",
                context={"target": spec.target.dir_name},
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 临时归档名（zip_builder 会在 output_path.parent 下创建
        # {tmp_archive}.zip），构建后 atomic replace 到最终路径
        tmp_archive = f".~tmp-{uuid.uuid4().hex[:8]}"

        try:
            tmp_zip = await self._builder.build(
                source_dir=str(source_dir),
                output_path=str(output_path.parent),
                archive_name=tmp_archive,
            )
            atomic_replace(Path(tmp_zip), output_path)
        except AtomicWriteError as e:
            raise PackagerError(
                f"ZIP 发布失败: {e}",
                context={"target": spec.target.dir_name},
            ) from e
        except Exception as e:
            raise PackagerError(
                f"ZIP 打包失败: {e}",
                context={"target": spec.target.dir_name},
            ) from e

        return OutputArtifact(
            path=str(output_path.resolve()),
            format="zip",
            target=spec.target,
            size=os.path.getsize(output_path),
        )
