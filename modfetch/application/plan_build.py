"""
PlanBuild 用例

将配置展开为不可变的 BuildPlan:
  version × loader 展开 → 逐 target 解析（模组/依赖/资源包/光影包/extra_urls）
  → 制品集合 + 输出规格集合

不做任何下载与打包（那是 ExecuteBuild 的职责）。
"""

from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from modfetch.application.dependency_resolver import DependencyGraphResolver
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import (
    ExtraUrl,
    FileType,
    ModEntry,
    ModFetchConfig,
    ModLoader,
    MrpackMode,
    OutputFormat,
)
from modfetch.ports.catalog import CatalogPort
from modfetch.services.mod_resolver import ModResolver
from modfetch.services.version_matcher import VersionMatcher

#: 解析阶段事件回调（插件 Hook 过渡桥）
#: async hook(name, *, version, mod_entry=None, extra_data=None)
PlanHook = Callable[..., Awaitable[None]]

#: mrpack env 标记（沿用旧契约）
_ENV_MOD = {"client": "required", "server": "required"}
_ENV_PACK = {"client": "required", "server": "optional"}


@dataclass
class PlanReport:
    """解析阶段的副产物（供统计与诊断）"""

    skipped_by_target: Dict[BuildTarget, Tuple[str, ...]] = field(
        default_factory=dict
    )


class PlanBuild:
    """构建计划生成用例"""

    def __init__(
        self,
        catalog: CatalogPort,
        dep_resolver: Optional[DependencyGraphResolver] = None,
        version_matcher: Optional[VersionMatcher] = None,
        hook: Optional[PlanHook] = None,
    ):
        self._catalog = catalog
        self._mod_resolver = ModResolver(catalog)
        self._dep_resolver = dep_resolver or DependencyGraphResolver(catalog)
        self._version_matcher = version_matcher or VersionMatcher(catalog)
        self._hook = hook

    @property
    def catalog(self) -> CatalogPort:
        return self._catalog

    async def execute(
        self, config: ModFetchConfig, features: Optional[List[str]] = None
    ) -> Tuple[BuildPlan, PlanReport]:
        features = features if features is not None else config.features

        targets = self._expand_targets(config)
        all_artifacts: List[ResolvedArtifact] = []
        all_outputs: List[OutputSpec] = []
        report = PlanReport()

        for target in targets:
            artifacts, skipped = await self._resolve_target(
                target, config, features
            )
            all_artifacts.extend(artifacts)
            report.skipped_by_target[target] = tuple(skipped)
            all_outputs.extend(self._make_output_specs(target, config))

        plan = BuildPlan(
            targets=tuple(targets),
            artifacts=tuple(all_artifacts),
            outputs=tuple(all_outputs),
            metadata={
                "name": config.metadata.name,
                "version": config.metadata.version,
                "description": config.metadata.description,
            },
        )
        return plan, report

    # -- 展开 -------------------------------------------------------------

    def _expand_targets(self, config: ModFetchConfig) -> List[BuildTarget]:
        return [
            BuildTarget(minecraft_version=version, loader=loader)
            for version in config.minecraft.version
            for loader in config.minecraft.loaders()
        ]

    def _make_output_specs(
        self, target: BuildTarget, config: ModFetchConfig
    ) -> List[OutputSpec]:
        specs: List[OutputSpec] = []
        metadata = config.metadata
        version = target.minecraft_version
        loader = target.loader.value

        if OutputFormat.MRPACK in config.output.format:
            for mode in config.output.mrpack_modes:
                # 多模式时附加 -{mode} 后缀（沿用旧命名契约）
                suffix = (
                    f"-{mode.value}"
                    if len(config.output.mrpack_modes) > 1
                    else ""
                )
                specs.append(
                    OutputSpec(
                        format="mrpack",
                        target=target,
                        output_name=(
                            f"{metadata.name}_{metadata.version}"
                            f"_MC{version}-{loader}{suffix}"
                        ),
                        mrpack_mode=mode.value,
                    )
                )

        if OutputFormat.ZIP in config.output.format:
            specs.append(
                OutputSpec(
                    format="zip",
                    target=target,
                    output_name=f"archive-{version}-{loader}",
                )
            )

        return specs

    # -- 单 target 解析 ----------------------------------------------------

    async def _resolve_target(
        self,
        target: BuildTarget,
        config: ModFetchConfig,
        features: List[str],
    ) -> Tuple[List[ResolvedArtifact], List[str]]:
        version = target.minecraft_version
        loader = target.loader
        artifacts: List[ResolvedArtifact] = []
        skipped: List[str] = []
        processed: Set[str] = set()  # per-target 去重（键: project_id）

        # 模组（含依赖）
        for mod in config.minecraft.mods:
            if not self._should_include(mod, version, features):
                continue

            mod_entry = mod if isinstance(mod, ModEntry) else None
            await self._emit_hook(
                "pre_resolve", version=version, mod_entry=mod_entry
            )

            result = await self._mod_resolver.resolve(mod, version, loader.value)
            if not result:
                skipped.append(str(mod))
                continue

            project_info, version_info, file_info = result
            await self._emit_hook(
                "post_resolve",
                version=version,
                mod_entry=mod_entry,
                extra_data={
                    "project_info": project_info,
                    "version_info": version_info,
                    "file_info": file_info,
                },
            )

            if project_info.id in processed:
                continue
            processed.add(project_info.id)
            artifacts.append(
                self._make_artifact(
                    target, project_info, file_info,
                    ArtifactCategory.mods(), _ENV_MOD,
                )
            )

            # 依赖
            await self._emit_hook(
                "pre_resolve_dependencies",
                version=version,
                extra_data={"version_info": version_info},
            )
            graph = await self._dep_resolver.resolve(
                version_info, version, loader.value
            )
            await self._emit_hook(
                "post_resolve_dependencies",
                version=version,
                extra_data={"dependencies": graph.nodes},
            )
            for dep_info, _, dep_file in graph.nodes:
                if dep_info.id in processed:
                    continue
                processed.add(dep_info.id)
                artifacts.append(
                    self._make_artifact(
                        target, dep_info, dep_file,
                        ArtifactCategory.mods(), _ENV_MOD,
                    )
                )

        # 资源包 / 光影包
        for entries, category in (
            (config.minecraft.resourcepacks, ArtifactCategory.resourcepacks()),
            (config.minecraft.shaderpacks, ArtifactCategory.shaderpacks()),
        ):
            for entry in entries:
                if not self._should_include(entry, version, features):
                    continue
                result = await self._mod_resolver.resolve(
                    entry, version, loader.value
                )
                if not result:
                    skipped.append(str(entry))
                    continue
                project_info, _, file_info = result
                artifacts.append(
                    self._make_artifact(
                        target, project_info, file_info, category, _ENV_PACK
                    )
                )

        # 额外 URL
        for extra in config.minecraft.extra_urls:
            if not self._should_include(extra, version, features):
                continue
            artifacts.append(self._make_extra_url_artifact(target, extra))

        return artifacts, skipped

    # -- 制品构造 -----------------------------------------------------------

    def _make_artifact(
        self,
        target: BuildTarget,
        project_info,
        file_info: dict,
        category: ArtifactCategory,
        env: Dict[str, str],
    ) -> ResolvedArtifact:
        filename = file_info["filename"]
        return ResolvedArtifact(
            project_id=project_info.id,
            project_name=project_info.name,
            category=category,
            filename=filename,
            url=file_info["url"],
            hashes=file_info.get("hashes") or {},
            destination=f"{category.value}/{filename}",
            target=target,
            size=file_info.get("size", 0),
            origin="catalog",
            environment=dict(env),
        )

    def _make_extra_url_artifact(
        self, target: BuildTarget, extra: ExtraUrl
    ) -> ResolvedArtifact:
        # type=file 放版本根目录；其他类型进入对应子目录
        # （沿用旧行为: pack→packs 复数化，MOD→"mod" 单数）
        url_basename = extra.url.rstrip("/").split("/")[-1]
        filename = extra.filename or url_basename
        if extra.type == FileType.FILE:
            category = ArtifactCategory.file()
            destination = filename
        else:
            category = ArtifactCategory(extra.type.value.replace("pack", "packs"))
            destination = f"{category.value}/{filename}"

        return ResolvedArtifact(
            project_id=f"extra_url:{extra.url}",
            project_name=filename,
            category=category,
            filename=filename,
            url=extra.url,
            hashes={"sha1": extra.sha1} if extra.sha1 else {},
            destination=destination,
            target=target,
            origin="extra_url",
        )

    # -- 过滤与事件 ---------------------------------------------------------

    def _should_include(
        self,
        entry: Union[str, ModEntry, ExtraUrl],
        version: str,
        features: List[str],
    ) -> bool:
        return self._version_matcher.should_include(entry, version, features)

    async def _emit_hook(self, name: str, **kwargs: Any) -> None:
        if self._hook is not None:
            await self._hook(name, **kwargs)
