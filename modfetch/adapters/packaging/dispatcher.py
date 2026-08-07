"""打包器分发器：按 OutputSpec.format 路由到具体 PackagerPort"""

from pathlib import Path
from typing import Dict

from modfetch.domain.build_plan import (
    BuildPlan,
    BuildTarget,
    OutputArtifact,
    OutputSpec,
)
from modfetch.domain.errors import PackagerError
from modfetch.ports.packager import PackagerPort


class PackagerDispatcher:
    """按格式分发的复合 PackagerPort"""

    def __init__(self, packagers: Dict[str, PackagerPort]):
        self._packagers = dict(packagers)

    def register(self, format: str, packager: PackagerPort) -> None:
        self._packagers[format] = packager

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        target: BuildTarget,
        workspace: Path,
    ) -> OutputArtifact:
        packager = self._packagers.get(spec.format)
        if packager is None:
            raise PackagerError(
                f"未注册的输出格式: {spec.format}",
                context={"format": spec.format},
            )
        return await packager.package(plan, spec, target, workspace)
