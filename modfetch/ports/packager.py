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
    """打包器接口

    契约约定：打包为同步语义的 async 操作，失败以 PackagerError 表达，
    调用方决定目标级失败语义（是否整次构建失败）。
    """

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        target: BuildTarget,
        workspace: Path,
    ) -> OutputArtifact:
        """将 workspace 中 target 对应的制品打包为输出文件

        实现期望：
            - 依据 plan.artifacts_for(target) 与 spec.format/mrpack_mode 组织内容
            - 产出文件写入 workspace（或约定输出目录），返回 OutputArtifact
            - 失败抛出 PackagerError，异常消息应含可诊断上下文

        Raises:
            PackagerError: 打包失败（调用方决定目标级失败语义）
        """
        ...
