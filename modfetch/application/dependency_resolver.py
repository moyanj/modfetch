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

    visited: Set[str] = field(default_factory=set)  # 已解析的 project_id（全局去重）
    visiting: List[str] = field(default_factory=list)  # 当前解析路径（循环检测，保序栈）
    resolved: List[Tuple[ProjectInfo, VersionInfo, dict]] = field(default_factory=list)  # (project, version, file)
    missing: List[str] = field(default_factory=list)  # 无法解析的 project_id（诊断用）
    cycles: List[List[str]] = field(default_factory=list)  # 检测到的环路径（project_id 序列）


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
        """解析 root 版本的全部 required 依赖（递归）

        Args:
            root: 依赖树的根版本信息
            mc_version: Minecraft 版本（依赖解析需匹配平台版本）
            loader: 加载器

        Returns:
            DependencyGraph: resolved 依赖列表 + missing 缺失项 +
            cycles 环路径；缺失与环仅记录诊断，不抛异常。
        """
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
        """递归解析依赖（深度优先，状态收敛到 ctx）

        仅处理 required 依赖；以 visiting 栈检测环、visited 集合
        避免重复展开。项目缺失或版本不可得时记入 missing。
        """
        for dep in version_info.dependencies:
            if dep.dependency_type != "required":
                # 可选依赖不参与下载解析（由模组自身运行时处理）
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
                # 当前 MC 版本/加载器下无匹配版本 → 记入 missing
                ctx.missing.append(dep_id)
                ctx.visiting.remove(dep_id)
                continue

            ctx.resolved.append((project, version, file_info))
            # 先记录本节点再递归其依赖，输出序为深度优先（根在前）
            await self._resolve_recursive(version, mc_version, loader, ctx)

            # 递归完成后出栈，使兄弟分支不再被误判为环
            ctx.visiting.remove(dep_id)
