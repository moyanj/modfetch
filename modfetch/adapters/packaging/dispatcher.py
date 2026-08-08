"""打包器分发器：按 OutputSpec.format 路由到具体 PackagerPort"""

from pathlib import Path
from typing import Dict

from modfetch.domain.build_plan import (
    BuildPlan,
    OutputArtifact,
    OutputSpec,
)
from modfetch.domain.errors import PackagerError
from modfetch.ports.packager import PackagerPort


class PackagerDispatcher:
    """按格式分发的复合 PackagerPort

    持有 {format: PackagerPort} 注册表，package() 按 OutputSpec.format
    路由到对应实现；未注册的格式抛 PackagerError。
    """

    def __init__(self, packagers: Dict[str, PackagerPort]):
        self._packagers = dict(packagers)

    def register(self, format: str, packager: PackagerPort) -> None:
        """注册格式 → 打包器映射（可在运行期补充）"""
        self._packagers[format] = packager

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        source_dir: Path,
        output_path: Path,
    ) -> OutputArtifact:
        """按 spec.format 路由到已注册的打包器

        显式接收 source_dir（工作区）与 output_path（最终产物路径）。

        Raises:
            PackagerError: 该格式未注册任何打包器
        """
        packager = self._packagers.get(spec.format)
        if packager is None:
            raise PackagerError(
                f"未注册的输出格式: {spec.format}",
                context={"format": spec.format},
            )
        return await packager.package(plan, spec, source_dir, output_path)