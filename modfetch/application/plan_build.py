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
from modfetch.application.mod_resolver import ModResolver
from modfetch.application.version_matcher import VersionMatcher
from modfetch.domain.events import BuildEvent, EventType
from modfetch.ports.catalog import CatalogPort
from modfetch.ports.event_sink import EventSink

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
    """构建计划生成用例

    将配置展开为不可变 BuildPlan: version × loader 展开 → 逐 target
    解析模组/依赖/资源包/光影包/extra_urls → 制品与输出规格集合。
    不做任何下载与打包（由 ExecuteBuild 承担）。
    """

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
        """对外的目录端口（供远程校验等复用同一 catalog 实例）"""
        return self._catalog

    async def execute(
        self,
        config: ModFetchConfig,
        features: Optional[List[str]] = None,
        event_sink: Optional[EventSink] = None,
        job_id: str = "",
    ) -> Tuple[BuildPlan, PlanReport]:
        """展开配置并生成构建计划

        Args:
            config: 用户配置
            features: 启用的功能标签；省略时使用 config.features
            event_sink: 解析阶段事件接收器（可选）
            job_id: 作业标识（事件关联用）

        Returns:
            (BuildPlan, PlanReport): 不可变构建计划与解析统计副产物
            （被跳过条目、依赖解析诊断等）。
        """
        features = features if features is not None else config.features
        self._sink = event_sink
        self._job_id = job_id

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
        """展开 version × loader 为全部构建目标（笛卡尔积）"""
        return [
            BuildTarget(minecraft_version=version, loader=loader)
            for version in config.minecraft.version
            for loader in config.minecraft.loaders()
        ]

    def _make_output_specs(
        self, target: BuildTarget, config: ModFetchConfig
    ) -> List[OutputSpec]:
        """为单个 target 生成输出规格（mrpack/zip）

        mrpack 多模式时以 -{mode} 后缀区分同名输出；zip 使用独立命名，
        避免与 mrpack 产物冲突。
        """
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
        """解析单个 target 的全部制品

        依次处理模组（含递归依赖）、资源包、光影包与 extra_urls，
        返回解析成功的制品列表；被过滤或解析失败的条目记入 skipped。

        Returns:
            (artifacts, skipped): 制品列表与跳过条目标识列表
        """
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
            mod_slug = (
                mod_entry.slug or mod_entry.id if mod_entry else str(mod)
            )
            await self._emit_event(
                EventType.RESOLVE_STARTED,
                target,
                {
                    "mod_slug": mod_slug or "unknown",
                    "mc_version": version,
                    "loader": loader.value,
                },
            )

            result = await self._mod_resolver.resolve(mod, version, loader.value)
            if not result:
                skipped.append(str(mod))
                await self._emit_event(
                    EventType.RESOLVE_FAILED,
                    target,
                    {"mod_slug": mod_slug or "unknown"},
                )
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
            await self._emit_event(
                EventType.RESOLVE_COMPLETED,
                target,
                {
                    "mod_slug": project_info.name,
                    "title": project_info.title,
                    "version": version_info.version,
                    "dependencies": len(version_info.dependencies),
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
            # 依赖制品与主模组共用同一 processed 去重集合，避免同项目重复打包
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
        """由解析结果构造标准制品（目录=category 名，含哈希与环境标记）"""
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
        """构造 extra_url 制品（非 catalog 来源，可带 sha1 校验）"""
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
        """按版本与功能标签过滤条目（委托 VersionMatcher）"""
        return self._version_matcher.should_include(entry, version, features)

    async def _emit_hook(self, name: str, **kwargs: Any) -> None:
        """触发解析阶段插件钩子（未注入 hook 时为空操作）"""
        if self._hook is not None:
            await self._hook(name, **kwargs)

    async def _emit_event(
        self, event_type: EventType, target: BuildTarget, payload: Dict[str, Any]
    ) -> None:
        """发布统一构建事件（提供 event_sink 时）"""
        if getattr(self, "_sink", None) is not None:
            await self._sink.publish(
                BuildEvent(
                    job_id=getattr(self, "_job_id", ""),
                    event_type=event_type,
                    payload={"target": target.dir_name, **payload},
                )
            )
