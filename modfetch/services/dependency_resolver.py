"""
依赖处理服务（向后兼容包装）

无状态实现已迁入 modfetch.application.dependency_resolver.DependencyGraphResolver。
本模块保留旧类名 DependencyResolver 与旧返回类型（list），
内部委托给无状态实现；实例级 _processed/_dependencies 仅作兼容占位。
"""

from typing import List, Set

from modfetch.application.dependency_resolver import (
    DependencyGraphResolver,
    DependencyGraph,  # noqa: F401 (兼容再导出)
)
from modfetch.domain.models import ProjectInfo, VersionInfo
from modfetch.ports.catalog import CatalogPort


class DependencyResolver:
    """旧接口兼容包装 — 委托给 DependencyGraphResolver"""

    def __init__(self, client: CatalogPort):
        self.client = client
        self._resolver = DependencyGraphResolver(client)
        # 兼容占位: 外部代码不应再依赖这两个集合
        self._processed: Set[str] = set()
        self._dependencies: List[tuple[ProjectInfo, VersionInfo, dict]] = []
        self.last_graph: DependencyGraph | None = None

    async def resolve(
        self,
        version_info: VersionInfo,
        mc_version: str,
        mod_loader: str,
    ) -> List[tuple[ProjectInfo, VersionInfo, dict]]:
        """解析依赖，返回与旧实现同构的列表"""
        graph = await self._resolver.resolve(version_info, mc_version, mod_loader)
        self.last_graph = graph
        return graph.nodes

    def clear_cache(self):
        """清除缓存（无状态实现下为 no-op，保留兼容）"""
        self._processed.clear()
        self._dependencies.clear()
