"""
远程配置校验（应用层）

从 services/project_validation.py 迁入:
- 通过 CatalogPort 访问平台，不直接依赖 ModrinthClient
- 条目级校验改为 asyncio.gather 并发（修复 N+1 串行问题）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Union

from modfetch.adapters.modrinth.facets import build_modrinth_facets  # noqa: F401 (兼容再导出)
from modfetch.application.version_matcher import VersionMatcher
from modfetch.domain.config_models import ModEntry, ModFetchConfig
from modfetch.domain.errors import ConfigValidationError
from modfetch.domain.models import ProjectType
from modfetch.ports.catalog import CatalogPort


@dataclass
class ValidationSuggestion:
    """校验失败时的候选推荐（供用户替换近似条目）"""

    slug: str
    project_id: str
    title: str
    project_type: str
    downloads: int = 0


@dataclass
class ValidationIssue:
    """单条目校验问题（含定位字段、错误码与候选建议）"""

    field: str
    code: str
    message: str
    identifier: str
    entry_type: str
    suggestions: list[ValidationSuggestion] = field(default_factory=list)
    context: dict[str, object] = field(default_factory=dict)


@dataclass
class ConfigValidationResult:
    """远程校验报告

    valid: 是否全部通过；issues: 未通过时的全部问题列表。
    """

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.valid


class ProjectValidationService:
    """逐条目远程校验: 存在性 → 类型 → 版本/加载器兼容性"""

    def __init__(self, catalog: CatalogPort):
        self.catalog = catalog
        #: 条件条目过滤（only_version/feature）——按版本粒度判断条目是否参与
        self._matcher = VersionMatcher()

    async def validate_config(
        self,
        config: ModFetchConfig,
        features: Optional[List[str]] = None,
    ) -> ConfigValidationResult:
        """校验配置中全部 mods/resourcepacks/shaderpacks 条目（并发）

        为每个条目构造校验任务并经 asyncio.gather 并发执行，
        单条失败不中断其余条目；返回聚合报告。

        Args:
            config: 待校验配置
            features: 启用的功能标签；省略时使用
                ``config.features``。仅通过 only_version/feature
                条件过滤的版本才会参与兼容性检查（与计划生成阶段的
                VersionMatcher 行为保持一致，避免误报不兼容）。
        """
        features = features if features is not None else config.features
        loaders = self._loader_values(config)

        # 构造 (entry, entry_type, field, loaders) 任务列表
        tasks = []
        for index, entry in enumerate(config.minecraft.mods):
            tasks.append(
                self.validate_entry(
                    entry=entry,
                    entry_type="mod",
                    field=f"minecraft.mods[{index}]",
                    mc_versions=config.minecraft.version,
                    loaders=loaders,
                    features=features,
                )
            )
        for index, entry in enumerate(config.minecraft.resourcepacks):
            tasks.append(
                self.validate_entry(
                    entry=entry,
                    entry_type="resourcepack",
                    field=f"minecraft.resourcepacks[{index}]",
                    mc_versions=config.minecraft.version,
                    loaders=[""],
                    features=features,
                )
            )
        for index, entry in enumerate(config.minecraft.shaderpacks):
            tasks.append(
                self.validate_entry(
                    entry=entry,
                    entry_type="shaderpack",
                    field=f"minecraft.shaderpacks[{index}]",
                    mc_versions=config.minecraft.version,
                    loaders=[""],
                    features=features,
                )
            )

        results = await asyncio.gather(*tasks)
        issues = [issue for issue in results if issue is not None]
        return ConfigValidationResult(valid=not issues, issues=issues)

    async def validate_entry(
        self,
        *,
        entry: Union[str, ModEntry],
        entry_type: str,
        field: str,
        mc_versions: Iterable[str],
        loaders: Iterable[str],
        features: Optional[List[str]] = None,
    ) -> Optional[ValidationIssue]:
        """校验单个条目: 存在性 → 类型 → 版本×加载器兼容性

        Args:
            entry: 待校验条目（字符串或 ModEntry 对象）
            entry_type: 条目类型（mod/resourcepack/shaderpack）
            field: 配置中的定位字段（如 "minecraft.mods[0]"）
            mc_versions: 配置声明的全部 Minecraft 版本
            loaders: 参与校验的加载器列表；空串表示不按加载器过滤
                （资源包/光影包仅按版本判定）
            features: 启用的功能标签；None 时对有 only_version/feature
                条件的条目依然要参与校验——本方法不自行过滤，
                由 validate_config 注入。

        Returns:
            None 表示通过；否则返回对应的 ValidationIssue
            （含 NOT_FOUND/TYPE_MISMATCH/INCOMPATIBLE 等错误码）。
            兼容性检查按 version × loader 并发执行。
        """
        identifier = self._entry_identifier(entry)
        if not identifier:
            return ValidationIssue(
                field=field,
                code="INVALID_ENTRY",
                message="条目缺少 slug 或 id",
                identifier="",
                entry_type=entry_type,
            )

        project = await self.catalog.get_project(identifier)
        if project is None:
            suggestions = await self._suggest(
                identifier, entry_type, mc_versions, loaders
            )
            return ValidationIssue(
                field=field,
                code="NOT_FOUND",
                message=f"未找到项目: {identifier}",
                identifier=identifier,
                entry_type=entry_type,
                suggestions=suggestions,
            )

        actual_type = self._project_type_value(project.project_type)
        expected_types = self._expected_project_types(entry_type)
        if actual_type not in expected_types:
            return ValidationIssue(
                field=field,
                code="TYPE_MISMATCH",
                message=f"项目 {identifier} 的类型是 {actual_type}，不能用于 {entry_type}",
                identifier=identifier,
                entry_type=entry_type,
                context={"actual_type": actual_type},
            )

        pinned_version = entry.version if isinstance(entry, ModEntry) else None

        # 版本×加载器兼容性检查并发执行。
        # 先按 (version, loader) 组合粒度过 only_version/only_loader/feature
        # 条件过滤：仅当条目在该组合实际生效时，才要求存在可用版本（与
        # 计划生成阶段 VersionMatcher.should_include 一致，避免误报不兼容）。
        # 资源包/光影包传入的 loader 为空串（无加载器上下文）→ 转 None，
        # 声明 only_loader 的条目因此不参与兼容性检查（由计划阶段判定）。
        applied_features = features or []
        pending_combos = [
            (mc_version, loader)
            for mc_version in mc_versions
            for loader in loaders
            if self._matcher.should_include(
                entry, mc_version, applied_features, loader or None
            )
        ]

        async def _check(mc_version: str, loader: str) -> Optional[str]:
            version_info, file_info = await self.catalog.get_version(
                project.id,
                mc_version,
                loader,
                specific_version=pinned_version,
            )
            if version_info is None or file_info is None:
                return f"{mc_version}/{loader}" if loader else mc_version
            return None

        checks = [
            _check(mc_version, loader)
            for mc_version, loader in pending_combos
        ]
        incompatible = [r for r in await asyncio.gather(*checks) if r is not None]

        if incompatible:
            return ValidationIssue(
                field=field,
                code="INCOMPATIBLE",
                message=f"项目 {identifier} 不兼容: {', '.join(incompatible)}",
                identifier=identifier,
                entry_type=entry_type,
                context={"incompatible_targets": incompatible},
            )

        return None

    async def _suggest(
        self,
        identifier: str,
        entry_type: str,
        mc_versions: Iterable[str],
        loaders: Iterable[str],
    ) -> list[ValidationSuggestion]:
        """按首个版本/加载器搜索近似项目，返回候选列表（最多 5 条）"""
        first_version = next(iter(mc_versions), None)
        first_loader = next(iter(loaders), "")
        candidates = await self.catalog.search(
            identifier,
            project_type=self._search_project_type(entry_type),
            mc_version=first_version,
            loader=first_loader or None,
            limit=5,
        )
        return [
            ValidationSuggestion(
                slug=candidate.name,
                project_id=candidate.id,
                title=candidate.title,
                project_type=self._project_type_value(candidate.project_type),
                downloads=getattr(candidate, "downloads", 0) or 0,
            )
            for candidate in candidates
        ]

    def _loader_values(self, config: ModFetchConfig) -> list[str]:
        """展开配置声明的加载器为枚举值列表"""
        return [loader.value for loader in config.minecraft.loaders()]

    def _entry_identifier(self, entry: Union[str, ModEntry]) -> Optional[str]:
        """提取条目查询标识（字符串条目本身即 slug；ModEntry 优先 id）"""
        if isinstance(entry, str):
            return entry
        return entry.id or entry.slug

    def _expected_project_types(self, entry_type: str) -> set[str]:
        """条目类型 → 允许的项目类型集合（兼容平台历史别名）"""
        mapping = {
            "mod": {"mod"},
            "resourcepack": {"resourcepack", "resource_pack"},
            "shaderpack": {"shaderpack", "shader"},
        }
        return mapping[entry_type]

    def _search_project_type(self, entry_type: str) -> str:
        """条目类型 → 平台搜索用的 project_type 参数"""
        mapping = {
            "mod": "mod",
            "resourcepack": "resourcepack",
            "shaderpack": "shader",
        }
        return mapping[entry_type]

    def _project_type_value(self, project_type: Union[str, ProjectType]) -> str:
        """归一化项目类型为字符串（兼容枚举与原生字符串）"""
        if isinstance(project_type, ProjectType):
            return project_type.value
        return str(project_type)


def format_validation_issues(issues: list[ValidationIssue]) -> str:
    """格式化问题列表为可读文本（含候选建议），供错误消息展示"""
    lines: list[str] = []
    for issue in issues:
        lines.append(f"{issue.field}: {issue.message}")
        if issue.suggestions:
            suggestion_list = ", ".join(
                f"{item.slug} ({item.title})" for item in issue.suggestions
            )
            lines.append(f"  候选: {suggestion_list}")
    return "\n".join(lines)


def validation_issue_to_dict(issue: ValidationIssue) -> dict[str, object]:
    """序列化单条问题为 dict（供 API 响应使用）"""
    return {
        "field": issue.field,
        "code": issue.code,
        "message": issue.message,
        "context": {
            **issue.context,
            "identifier": issue.identifier,
            "entry_type": issue.entry_type,
            "suggestions": [
                {
                    "slug": item.slug,
                    "project_id": item.project_id,
                    "title": item.title,
                    "project_type": item.project_type,
                    "downloads": item.downloads,
                }
                for item in issue.suggestions
            ],
        },
    }


async def ensure_remote_config_valid(
    config: ModFetchConfig,
    *,
    client: Optional[CatalogPort] = None,
    catalog: Optional[CatalogPort] = None,
) -> None:
    """远程校验，失败抛 ConfigValidationError

    client 参数为旧名，保持兼容。
    """
    port = catalog or client
    if port is None:
        raise ValueError("必须提供 catalog 或 client")
    service = ProjectValidationService(port)
    result = await service.validate_config(config)
    if result.valid:
        return
    raise ConfigValidationError(format_validation_issues(result.issues))
