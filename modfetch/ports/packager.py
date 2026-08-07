"""打包端口"""

from pathlib import Path
from typing import Protocol

from modfetch.domain.build_plan import (
    BuildPlan,
    BuildTarget,
    OutputArtifact,
    OutputSpec,
)


class PackagerPort(Protocol):
    """打包器接口"""

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        target: BuildTarget,
        workspace: Path,
    ) -> OutputArtifact:
        """将 workspace 中 target 对应的制品打包为输出文件

        Raises:
            PackagerError: 打包失败（调用方决定目标级失败语义）
        """
        ...
