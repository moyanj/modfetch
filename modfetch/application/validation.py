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
from modfetch.domain.config_models import ModEntry, ModFetchConfig
from modfetch.domain.errors import ConfigValidationError
from modfetch.domain.models import ProjectType
from modfetch.ports.catalog import CatalogPort


@dataclass
class ValidationSuggestion:
    slug: str
    project_id: str
    title: str
    project_type: str
    downloads: int = 0


@dataclass
class ValidationIssue:
    field: str
    code: str
    message: str
    identifier: str
    entry_type: str
    suggestions: list[ValidationSuggestion] = field(default_factory=list)
    context: dict[str, object] = field(default_factory=dict)


@dataclass
class ConfigValidationResult:
    """远程校验报告（ValidationReport）"""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.valid


class ProjectValidationService:
    """逐条目远程校验: 存在性 → 类型 → 版本/加载器兼容性"""

    def __init__(self, catalog: CatalogPort):
        self.catalog = catalog

    async def validate_config(self, config: ModFetchConfig) -> ConfigValidationResult:
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
    ) -> Optional[ValidationIssue]:
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

        # 版本×加载器兼容性检查并发执行
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
            for mc_version in mc_versions
            for loader in loaders
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
        return [loader.value for loader in config.minecraft.loaders()]

    def _entry_identifier(self, entry: Union[str, ModEntry]) -> Optional[str]:
        if isinstance(entry, str):
            return entry
        return entry.id or entry.slug

    def _expected_project_types(self, entry_type: str) -> set[str]:
        mapping = {
            "mod": {"mod"},
            "resourcepack": {"resourcepack", "resource_pack"},
            "shaderpack": {"shaderpack", "shader"},
        }
        return mapping[entry_type]

    def _search_project_type(self, entry_type: str) -> str:
        mapping = {
            "mod": "mod",
            "resourcepack": "resourcepack",
            "shaderpack": "shader",
        }
        return mapping[entry_type]

    def _project_type_value(self, project_type: Union[str, ProjectType]) -> str:
        if isinstance(project_type, ProjectType):
            return project_type.value
        return str(project_type)


def format_validation_issues(issues: list[ValidationIssue]) -> str:
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
