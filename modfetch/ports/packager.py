"""打包端口"""

from pathlib import Path
from typing import Protocol

from modfetch.domain.build_plan import (
    BuildPlan,
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
        source_dir: Path,
        output_path: Path,
    ) -> OutputArtifact:
        """将 source_dir 中的制品打包为 output_path 指向的产物文件

        显式接收源目录与最终输出路径，打包器不再自行猜测工作区结构：
            - source_dir: target 打包工作区（含 mods/resourcepacks/... 子目录）
            - output_path: 最终产物完整路径（含扩展名），父目录已存在

        实现期望：
            - 依据 plan.artifacts_for(spec.target) 与 spec.format/mrpack_mode 组织内容
            - 产出文件先写 output_path 同目录的临时文件，成功后原子替换
            - 失败抛出 PackagerError，异常消息应含可诊断上下文

        Raises:
            PackagerError: 打包失败（调用方决定目标级失败语义）
        """
        ...
