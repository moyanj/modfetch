"""
Mrpack 打包器（PackagerPort 实现）

与旧编排的差异:
- 文件列表来自 BuildPlan.artifacts（不再依赖实例状态）
- 失败抛出 PackagerError（调用方决定 target 级失败语义）
- 返回结构化 OutputArtifact
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, Optional

from modfetch.domain.build_plan import (
    BuildPlan,
    BuildTarget,
    OutputArtifact,
    OutputSpec,
)
from modfetch.adapters.packaging.mrpack_builder import MrpackBuilder
from modfetch.domain.config_models import ModLoader, MrpackMode
from modfetch.domain.errors import PackagerError

#: 加载器版本解析回调: async (loader, mc_version) -> version_str
LoaderVersionResolver = Callable[[ModLoader, str], Awaitable[Optional[str]]]


class MrpackPackager:
    """Mrpack 打包器（实现 PackagerPort）

    按 OutputSpec 为单个构建目标生成 .mrpack 整合包，支持两种模式：
    - download: 下载的制品物理复制到 overrides/，manifest.files 保持空
    - reference: 制品仅以引用（path/hashes/env/downloads）写入
      manifest.files，模组文件不落入包内，客户端按引用自行下载
    """

    def __init__(
        self,
        loader_version_resolver: Optional[LoaderVersionResolver] = None,
        metadata: Optional[dict] = None,
    ):
        self._builder = MrpackBuilder()
        self._loader_version_resolver = loader_version_resolver
        self._metadata = metadata or {}

    async def package(
        self,
        plan: BuildPlan,
        spec: OutputSpec,
        target: BuildTarget,
        workspace: Path,
    ) -> OutputArtifact:
        """按 OutputSpec 打包单个 target 为 .mrpack

        两种模式差异（见类 docstring）：
        - download: source_dir 直接作为 overrides 源目录
        - reference: overrides 仅含 extra_urls 文件，catalog 制品转为
          manifest.files 引用（env 标记沿用 ResolvedArtifact.environment，
          默认 client/server 均 required）

        Raises:
            PackagerError: 格式不支持，或打包过程失败
        """
        if spec.format != "mrpack":
            raise PackagerError(f"MrpackPackager 不支持格式: {spec.format}")

        mode = MrpackMode(spec.mrpack_mode)
        # 源目录约定: workspace/{target.dir_name} = workspace/{MC版本}-{加载器}
        source_dir = workspace / target.dir_name
        source_dir.mkdir(parents=True, exist_ok=True)

        loader_version = None
        if self._loader_version_resolver is not None:
            # 查询当前 MC 版本 × 加载器对应的加载器版本（写入 manifest 依赖）
            loader_version = await self._loader_version_resolver(
                target.loader, target.minecraft_version
            )

        # 优先使用 plan 携带的元数据，回退到构造期默认值
        source = plan.metadata or self._metadata
        metadata = {
            "name": source.get("name", "ModFetch Pack"),
            "version": source.get("version", "1.0.0"),
            "description": source.get("description", ""),
        }

        # REFERENCE 模式: overrides 只含 extra_urls 文件
        # （DOWNLOAD 模式下 source_dir 直接充当 overrides 源）
        actual_source = source_dir
        temp_overrides: Optional[str] = None
        if mode == MrpackMode.REFERENCE:
            actual_source, temp_overrides = self._prepare_reference_overrides(
                plan, target, source_dir
            )

        files = (
            # REFERENCE 模式: 仅 catalog 来源的制品写入 manifest.files 引用
            [
                artifact.to_mrpack_entry()
                for artifact in plan.artifacts_for(target)
                if artifact.origin == "catalog"
            ]
            if mode == MrpackMode.REFERENCE
            else None
        )

        output_path = workspace / spec.output_name

        try:
            mrpack_path = await self._builder.build(
                source_dir=str(actual_source),
                output_path=str(output_path),
                metadata=metadata,
                mc_version=target.minecraft_version,
                mod_loader=target.loader,
                loader_version=loader_version,
                files=files,
            )
        except Exception as e:
            raise PackagerError(
                f"mrpack ({mode.value}) 打包失败: {e}",
                context={"target": target.dir_name, "mode": mode.value},
            ) from e
        finally:
            # 清理 REFERENCE 模式的临时 overrides（DOWNLOAD 模式为 None）
            if temp_overrides and os.path.exists(temp_overrides):
                shutil.rmtree(temp_overrides)

        return OutputArtifact(
            path=mrpack_path,
            format="mrpack",
            target=target,
            size=os.path.getsize(mrpack_path),
        )

    def _prepare_reference_overrides(
        self, plan: BuildPlan, target: BuildTarget, source_dir: Path
    ) -> tuple[Path, Optional[str]]:
        """REFERENCE 模式: 默认空目录；有 extra_urls 时复制到临时 overrides

        返回 (overrides 源目录, 临时目录路径)：
        - 无 extra_urls: 返回空目录占位，mrpack 仍含空的 overrides/ 入口
        - 有 extra_urls: 复制到独立临时目录（保持相对结构），由调用方清理
        """
        # 收集 extra_url 来源的制品，其 destination 为相对 source_dir 的路径
        destinations = [
            source_dir / artifact.destination
            for artifact in plan.artifacts_for(target)
            if artifact.origin == "extra_url"
        ]

        if not destinations:
            # 空占位目录：确保 overrides/ 存在但无实际内容
            empty = source_dir / "non_existent_empty_dir"
            empty.mkdir(parents=True, exist_ok=True)
            return empty, None

        # 独立临时目录，避免污染版本目录
        extra_source = tempfile.mkdtemp(prefix="modfetch_extra_overrides_")
        for dest in destinations:
            if not dest.exists():
                continue
            # 保持相对路径结构映射到临时 overrides 根
            rel_path = dest.relative_to(source_dir)
            override_dest = Path(extra_source) / rel_path
            if dest.is_dir():
                shutil.copytree(dest, override_dest, dirs_exist_ok=True)
            else:
                override_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, override_dest)
        return Path(extra_source), extra_source
