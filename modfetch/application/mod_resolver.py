"""
模组解析用例（自 services.mod_resolver 迁移）

处理模组 ID/slug 解析、版本匹配，返回标准化的模组信息。
仅依赖 CatalogPort，不耦合具体平台客户端。
"""

from typing import List, Optional, Union

from loguru import logger

from modfetch.domain.config_models import ModEntry
from modfetch.domain.models import ProjectInfo, VersionInfo
from modfetch.ports.catalog import CatalogPort


class ModResolver:
    """模组解析器（带项目信息缓存）"""

    def __init__(self, catalog: CatalogPort):
        self.catalog = catalog
        self._cache: dict[str, ProjectInfo] = {}

    async def resolve(
        self,
        mod: Union[str, ModEntry],
        mc_version: str,
        mod_loader: str,
    ) -> Optional[tuple[ProjectInfo, VersionInfo, dict]]:
        """
        解析模组信息

        Args:
            mod: 模组 ID 或 ModEntry
            mc_version: Minecraft 版本
            mod_loader: 模组加载器

        Returns:
            tuple: (project_info, version_info, file_info) 或 None

        过程: 提取标识与固定版本 → 查询项目（带缓存）→ 查询匹配版本；
        返回 None 表示项目不存在或当前 MC 版本/加载器下无匹配版本。
        """
        # 提取模组标识和版本固定信息
        if isinstance(mod, str):
            mod_id = mod
            pinned_version = None
        else:
            mod_id = mod.id or mod.slug
            pinned_version = mod.version

        if not mod_id:
            logger.warning(f"[resolve] 模组无有效 ID/slug: {mod!r}")
            return None

        # 获取项目信息（使用缓存）
        if mod_id in self._cache:
            project_info = self._cache[mod_id]
            logger.debug(f"[resolve] 缓存命中: {mod_id} -> {project_info.name}")
        else:
            project_info = await self.catalog.get_project(mod_id)
            if project_info:
                self._cache[mod_id] = project_info
                logger.debug(
                    f"[resolve] 查询到项目: {mod_id} -> {project_info.name}"
                )

        if not project_info:
            logger.warning(
                f"[resolve] 项目不存在或获取失败: {mod_id} "
                f"(mc={mc_version}, loader={mod_loader})"
            )
            return None

        # 获取版本信息（支持版本固定）
        version_info, file_info = await self.catalog.get_version(
            project_info.id,
            mc_version,
            mod_loader,
            specific_version=pinned_version,
        )

        if not version_info or not file_info:
            logger.warning(
                f"[resolve] 无匹配版本: {project_info.name} ({mod_id}) "
                f"mc={mc_version} loader={mod_loader} "
                f"pinned={pinned_version or 'latest'}"
            )
            return None

        logger.debug(
            f"[resolve] 解析成功: {project_info.name} ({mod_id}) "
            f"-> version={version_info.version}, "
            f"file={file_info.get('filename')}"
        )
        return project_info, version_info, file_info

    async def resolve_many(
        self,
        mods: List[Union[str, ModEntry]],
        mc_version: str,
        mod_loader: str,
    ) -> List[tuple[ProjectInfo, VersionInfo, dict]]:
        """批量解析模组

        串行逐条 resolve 以复用项目信息缓存（避免重复网络请求）；
        无法解析的条目不进入结果列表（调用方可据长度感知缺失）。
        """
        results = []
        for mod in mods:
            result = await self.resolve(mod, mc_version, mod_loader)
            if result:
                results.append(result)
        return results