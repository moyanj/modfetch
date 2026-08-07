"""
无状态依赖图解析器（应用层）

与旧 services/dependency_resolver.py 的差异:
- 实例不再持有 _processed/_dependencies 可变状态（并发安全）
- 每次 resolve() 创建独立的 ResolveContext
- 循环依赖产生结构化诊断（cycles）而非静默跳过
- 缺失依赖记录到 missing 而非静默忽略
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from modfetch.domain.models import ProjectInfo, VersionInfo
from modfetch.ports.catalog import CatalogPort


@dataclass
class ResolveContext:
    """per-call 解析状态（局部化，不挂在实例上）"""

    visited: Set[str] = field(default_factory=set)
    visiting: List[str] = field(default_factory=list)  # 循环检测（保序栈）
    resolved: List[Tuple[ProjectInfo, VersionInfo, dict]] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)


@dataclass
class DependencyGraph:
    """依赖解析结果"""

    nodes: List[Tuple[ProjectInfo, VersionInfo, dict]]
    missing: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)

    def __iter__(self):
        """兼容旧的 for dep_info, dep_version, dep_file in deps 用法"""
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)


class DependencyGraphResolver:
    """无状态依赖解析器 — 实例仅持有 catalog 端口"""

    def __init__(self, catalog: CatalogPort):
        self._catalog = catalog

    async def resolve(
        self,
        root: VersionInfo,
        mc_version: str,
        loader: str,
    ) -> DependencyGraph:
        """解析 root 版本的全部 required 依赖（递归）"""
        ctx = ResolveContext()
        await self._resolve_recursive(root, mc_version, loader, ctx)
        return DependencyGraph(
            nodes=ctx.resolved,
            missing=ctx.missing,
            cycles=ctx.cycles,
        )

    async def _resolve_recursive(
        self,
        version_info: VersionInfo,
        mc_version: str,
        loader: str,
        ctx: ResolveContext,
    ) -> None:
        for dep in version_info.dependencies:
            if dep.dependency_type != "required":
                continue

            dep_id = dep.project_id

            # 循环检测: 当前解析路径上再次出现
            if dep_id in ctx.visiting:
                ctx.cycles.append([*ctx.visiting, dep_id])
                continue

            if dep_id in ctx.visited:
                continue

            ctx.visiting.append(dep_id)
            ctx.visited.add(dep_id)

            project = await self._catalog.get_project(dep_id)
            if project is None:
                ctx.missing.append(dep_id)
                ctx.visiting.remove(dep_id)
                continue

            version, file_info = await self._catalog.get_version(
                dep_id, mc_version, loader
            )
            if version is None or file_info is None:
                ctx.missing.append(dep_id)
                ctx.visiting.remove(dep_id)
                continue

            ctx.resolved.append((project, version, file_info))
            await self._resolve_recursive(version, mc_version, loader, ctx)

            ctx.visiting.remove(dep_id)
