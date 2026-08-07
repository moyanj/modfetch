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
from modfetch.domain.config_models import ModLoader, MrpackMode
from modfetch.domain.errors import PackagerError
from modfetch.packager.mrpack import MrpackBuilder

#: 加载器版本解析回调: async (loader, mc_version) -> version_str
LoaderVersionResolver = Callable[[ModLoader, str], Awaitable[Optional[str]]]


class MrpackPackager:
    """Mrpack 打包器（实现 PackagerPort）"""

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
        if spec.format != "mrpack":
            raise PackagerError(f"MrpackPackager 不支持格式: {spec.format}")

        mode = MrpackMode(spec.mrpack_mode)
        source_dir = workspace / target.dir_name
        source_dir.mkdir(parents=True, exist_ok=True)

        loader_version = None
        if self._loader_version_resolver is not None:
            loader_version = await self._loader_version_resolver(
                target.loader, target.minecraft_version
            )

        metadata = {
            "name": self._metadata.get("name", "ModFetch Pack"),
            "version": self._metadata.get("version", "1.0.0"),
            "description": self._metadata.get("description", ""),
        }

        # REFERENCE 模式: overrides 只含 extra_urls 文件
        actual_source = source_dir
        temp_overrides: Optional[str] = None
        if mode == MrpackMode.REFERENCE:
            actual_source, temp_overrides = self._prepare_reference_overrides(
                plan, target, source_dir
            )

        files = (
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
        """REFERENCE 模式: 默认空目录；有 extra_urls 时复制到临时 overrides"""
        destinations = [
            source_dir / artifact.destination
            for artifact in plan.artifacts_for(target)
            if artifact.origin == "extra_url"
        ]

        if not destinations:
            empty = source_dir / "non_existent_empty_dir"
            empty.mkdir(parents=True, exist_ok=True)
            return empty, None

        extra_source = tempfile.mkdtemp(prefix="modfetch_extra_overrides_")
        for dest in destinations:
            if not dest.exists():
                continue
            rel_path = dest.relative_to(source_dir)
            override_dest = Path(extra_source) / rel_path
            if dest.is_dir():
                shutil.copytree(dest, override_dest, dirs_exist_ok=True)
            else:
                override_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, override_dest)
        return Path(extra_source), extra_source
