"""ZIP 打包器（PackagerPort 实现）"""

import os
from pathlib import Path

from modfetch.domain.build_plan import (
    BuildPlan,
    BuildTarget,
    OutputArtifact,
    OutputSpec,
)
from modfetch.adapters.packaging.zip_builder import ZipBuilder
from modfetch.domain.errors import PackagerError


class ZipPackager:
    """ZIP 打包器（实现 PackagerPort）"""

    def __init__(self):
        self._builder = ZipBuilder()

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        target: BuildTarget,
        workspace: Path,
    ) -> OutputArtifact:
        if spec.format != "zip":
            raise PackagerError(f"ZipPackager 不支持格式: {spec.format}")

        source_dir = workspace / target.dir_name
        if not source_dir.exists():
            raise PackagerError(
                f"源目录不存在: {source_dir}",
                context={"target": target.dir_name},
            )

        try:
            zip_path = await self._builder.build(
                source_dir=str(source_dir),
                output_path=str(workspace),
                archive_name=spec.output_name,
            )
        except Exception as e:
            raise PackagerError(
                f"ZIP 打包失败: {e}",
                context={"target": target.dir_name},
            ) from e

        return OutputArtifact(
            path=zip_path,
            format="zip",
            target=target,
            size=os.path.getsize(zip_path),
        )
