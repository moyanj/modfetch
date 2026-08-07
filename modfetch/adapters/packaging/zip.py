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
    """ZIP 打包器（实现 PackagerPort）

    将单个构建目标目录压缩为 .zip 归档。
    """

    def __init__(self):
        self._builder = ZipBuilder()

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        target: BuildTarget,
        workspace: Path,
    ) -> OutputArtifact:
        """按 OutputSpec 打包单个 target 为 .zip

        归档内容为 workspace/{target.dir_name}（{MC版本}-{加载器} 目录）
        下的所有已下载制品。

        Raises:
            PackagerError: 格式不支持 / 源目录缺失 / 压缩失败
        """
        if spec.format != "zip":
            raise PackagerError(f"ZipPackager 不支持格式: {spec.format}")

        # 源目录约定: workspace/{MC版本}-{加载器}，须在打包前已存在
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
            # 统一包装为 PackagerError，附带目标上下文
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
