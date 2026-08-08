"""CatalogPort 缓存装饰器（请求聚合）

包装任意 CatalogPort 实现，为高频查询（get_project / get_version /
get_loader_version）增加进程内缓存与 single-flight 并发合并，消除
构建流程中的重复外部请求：

- **多 target / 多版本**：同一 (mod, mc_version, loader) 组合的
  get_version 在多 target 间被重复请求；缓存后仅首个 target 触发。
- **依赖共享**：多个模组依赖同一公共库（fabric-api 等）时，其
  get_project / get_version 被重复展开；缓存后只查询一次。
- **多 mrpack 模式**：同一 (loader, mc_version) 的 loader 版本被
  打包阶段重复获取；缓存后一次即得。
- **404/无匹配**：negative 结果也缓存，避免对缺失项目反复请求。

single-flight 语义：同一 key 的并发请求合并为一个底层调用，其余
调用方 await 同一任务；组 build target 未来并行化时不产生重复请求。

生命周期对齐：composition 每次 create_build_service 新建实例，而
作业级 service（Web）每次任务 start 时重新组装并 close，故缓存
生命周期不大于单个 job，不跨任务污染数据。
"""

import asyncio
from typing import Dict, Optional, Tuple

from modfetch.domain.models import ProjectInfo, VersionInfo
from modfetch.ports.catalog import CatalogPort

#: get_version 缓存键: (project_id, mc_version, loader, specific_version)
_VersionKey = Tuple[str, str, str, Optional[str]]
#: get_loader_version 缓存键: (loader, mc_version)
_LoaderKey = Tuple[str, str]


class CachingCatalog:
    """CatalogPort 缓存装饰器（请求聚合 + single-flight）

    组合包装底层 CatalogPort，不改触发布协议；除缓存外行为与之等价，
    返回值与透传完全一致（含 None/异常）。close 透传给内层实现。
    """

    def __init__(self, inner: CatalogPort) -> None:
        self._inner = inner
        #: project 索引缓存: identifier → ProjectInfo | None（None 亦缓存）
        self._projects: Dict[str, Optional[ProjectInfo]] = {}
        #: version 索引缓存: key → (VersionInfo, file_info)（缺失存 (None, None)）
        self._versions: Dict[_VersionKey, Tuple[Optional[VersionInfo], Optional[dict]]] = {}
        #: loader 版本缓存: key → Optional[str]
        self._loader_versions: Dict[_LoaderKey, Optional[str]] = {}

        #: single-flight: key → in-flight 请求任务
        self._inflight_project: Dict[str, "asyncio.Task[Optional[ProjectInfo]]"] = {}
        self._inflight_version: Dict[_VersionKey, "asyncio.Task[Tuple[Optional[VersionInfo], Optional[dict]]]"] = {}
        self._inflight_loader: Dict[_LoaderKey, "asyncio.Task[Optional[str]]"] = {}

    # -- CatalogPort 实现 ----------------------------------------------------

    async def get_project(self, identifier: str) -> Optional[ProjectInfo]:
        """按 ID/slug 取项目（缓存 + single-flight）"""
        if identifier in self._projects:
            return self._projects[identifier]

        task = self._inflight_project.get(identifier)
        if task is None:
            task = asyncio.create_task(self._load_project(identifier))
            self._inflight_project[identifier] = task
        try:
            return await task
        finally:
            self._inflight_project.pop(identifier, None)

    async def get_version(
        self,
        project_id: str,
        mc_version: str,
        loader: str,
        specific_version: Optional[str] = None,
    ) -> Tuple[Optional[VersionInfo], Optional[dict]]:
        """取兼容版本与主文件（缓存 + single-flight）"""
        key = (project_id, mc_version, loader, specific_version)
        if key in self._versions:
            return self._versions[key]

        task = self._inflight_version.get(key)
        if task is None:
            task = asyncio.create_task(self._load_version(key))
            self._inflight_version[key] = task
        try:
            return await task
        finally:
            self._inflight_version.pop(key, None)

    async def get_loader_version(
        self, loader: str, mc_version: str
    ) -> Optional[str]:
        """获取加载器版本（缓存 + single-flight）"""
        key = (loader, mc_version)
        if key in self._loader_versions:
            return self._loader_versions[key]

        task = self._inflight_loader.get(key)
        if task is None:
            task = asyncio.create_task(self._load_loader_version(key))
            self._inflight_loader[key] = task
        try:
            return await task
        finally:
            self._inflight_loader.pop(key, None)

    async def search(
        self,
        query: str,
        *,
        project_type: Optional[str] = None,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 5,
    ) -> list[ProjectInfo]:
        """搜索项目（透传，搜索结果不缓存）"""
        return await self._inner.search(
            query,
            project_type=project_type,
            mc_version=mc_version,
            loader=loader,
            limit=limit,
        )

    async def close(self) -> None:
        """释放内层资源（透传）"""
        await self._inner.close()

    # -- 内部缓存加载 -------------------------------------------------------

    async def _load_project(self, identifier: str) -> Optional[ProjectInfo]:
        result = await self._inner.get_project(identifier)
        self._projects[identifier] = result
        return result

    async def _load_version(
        self, key: _VersionKey
    ) -> Tuple[Optional[VersionInfo], Optional[dict]]:
        result = await self._inner.get_version(*key)
        self._versions[key] = result
        return result

    async def _load_loader_version(self, key: _LoaderKey) -> Optional[str]:
        result = await self._inner.get_loader_version(*key)
        self._loader_versions[key] = result
        return result

    # -- 辅助（供测试/诊断） ----------------------------------------------

    @property
    def project_cache_size(self) -> int:
        """已缓存 project 条目数（诊断用）"""
        return len(self._projects)

    def clear(self) -> None:
        """清空全部缓存（诊断/测试用）"""
        self._projects.clear()
        self._versions.clear()
        self._loader_versions.clear()