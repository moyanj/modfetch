"""
模组解析服务

处理模组 ID/slug 解析、版本匹配，返回标准化的模组信息。
"""

from typing import Optional, Union, List

from modfetch.models import ModEntry, ProjectInfo, VersionInfo
from modfetch.services.api_client import ModrinthClient
from modfetch.exceptions import APIError


class ModResolver:
    """模组解析器"""

    def __init__(self, client: ModrinthClient):
        self.client = client
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
        """
        # 提取模组标识
        if isinstance(mod, str):
            mod_id = mod
        else:
            mod_id = mod.id or mod.slug

        if not mod_id:
            return None

        # 获取项目信息（使用缓存）
        if mod_id in self._cache:
            project_info = self._cache[mod_id]
        else:
            project_info = await self.client.get_project(mod_id)
            if project_info:
                self._cache[mod_id] = project_info

        if not project_info:
            return None

        # 获取版本信息
        version_info, file_info = await self.client.get_version(
            project_info.id, mc_version, mod_loader
        )

        if not version_info or not file_info:
            return None

        return project_info, version_info, file_info

    async def resolve_many(
        self,
        mods: List[Union[str, ModEntry]],
        mc_version: str,
        mod_loader: str,
    ) -> List[tuple[ProjectInfo, VersionInfo, dict]]:
        """
        批量解析模组

        Args:
            mods: 模组列表
            mc_version: Minecraft 版本
            mod_loader: 模组加载器

        Returns:
            解析成功的模组信息列表
        """
        results = []
        for mod in mods:
            result = await self.resolve(mod, mc_version, mod_loader)
            if result:
                results.append(result)
        return results
