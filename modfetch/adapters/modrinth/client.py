"""
Modrinth API 客户端

实现 CatalogPort。仅负责 HTTP 与 JSON 映射，不含业务流程。
"""

from typing import List, Optional, Tuple

import aiohttp

from modfetch.adapters.modrinth.facets import build_modrinth_facets
from modfetch.adapters.modrinth.mapper import (
    map_project,
    map_search_hit,
    map_version,
    pick_primary_file,
)
from modfetch.domain.errors import APIError
from modfetch.domain.models import ProjectInfo, VersionInfo

MODRINTH_BASE_URL = "https://api.modrinth.com/v2"

_LOADER_META_URLS = {
    "fabric": "https://meta.fabricmc.net/v2/versions/loader/{mc_version}",
    "quilt": "https://meta.quiltmc.org/v3/versions/loader/{mc_version}",
}


class ModrinthClient:
    """Modrinth API 客户端（CatalogPort 实现）"""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owned_session = session is None

    @property
    def session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(
        self, endpoint: str, params: Optional[dict] = None
    ) -> Optional[dict]:
        """发送 API 请求；404 返回 None，其他错误抛 APIError"""
        async with self.session.get(endpoint, params=params) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return None
            else:
                raise APIError(
                    f"API 请求失败 (状态码: {response.status})",
                    status_code=response.status,
                    url=str(response.url),
                )

    async def raw_get(
        self, path: str, params: Optional[dict] = None
    ) -> Tuple[int, Optional[object]]:
        """裸 GET 透传（供路由层代理 Modrinth API，返回 (status, json)）"""
        async with self.session.get(
            f"{MODRINTH_BASE_URL}{path}", params=params
        ) as response:
            if response.status == 200:
                return 200, await response.json()
            return response.status, None

    async def get_project(self, identifier: str) -> Optional[ProjectInfo]:
        """获取项目信息"""
        response = await self._request(f"{MODRINTH_BASE_URL}/project/{identifier}")
        if response is None:
            return None
        return map_project(response)

    async def search(
        self,
        query: str,
        *,
        project_type: Optional[str] = None,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 5,
    ) -> List[ProjectInfo]:
        """搜索项目（CatalogPort）"""
        return await self.search_projects(
            query,
            project_type=project_type,
            mc_version=mc_version,
            mod_loader=loader,
            limit=limit,
        )

    async def search_projects(
        self,
        query: str,
        *,
        project_type: Optional[str] = None,
        mc_version: Optional[str] = None,
        mod_loader: Optional[str] = None,
        limit: int = 5,
    ) -> List[ProjectInfo]:
        """搜索项目（旧方法名，保持兼容）"""
        params = {
            "query": query,
            "limit": str(limit),
        }
        facets = build_modrinth_facets(
            project_type=project_type,
            mc_version=mc_version,
            mod_loader=mod_loader,
        )
        if facets:
            params["facets"] = facets

        response = await self._request(f"{MODRINTH_BASE_URL}/search", params=params)
        if response is None:
            return []
        return [map_search_hit(item) for item in response.get("hits", [])]

    async def get_version(
        self,
        project_id: str,
        mc_version: str,
        loader: str,
        specific_version: Optional[str] = None,
    ) -> Tuple[Optional[VersionInfo], Optional[dict]]:
        """获取兼容的版本信息与主文件

        Returns:
            (VersionInfo, file_info)；指定版本未找到时不降级到最新版本
        """
        params = {"game_versions": f'["{mc_version}"]'}
        if loader:
            params["loaders"] = f'["{loader}"]'

        response = await self._request(
            f"{MODRINTH_BASE_URL}/project/{project_id}/version", params
        )

        if response is None or len(response) == 0:
            return None, None

        if specific_version:
            for version in response:
                if (
                    version["id"] == specific_version
                    or version["version_number"] == specific_version
                ):
                    return map_version(version), pick_primary_file(version)
            return None, None

        version = response[0]
        return map_version(version), pick_primary_file(version)

    async def get_loader_version(
        self, loader: str, mc_version: str
    ) -> Optional[str]:
        """获取加载器版本（CatalogPort 统一入口）"""
        if loader == "fabric":
            return await self._get_meta_loader_version("fabric", mc_version)
        if loader == "quilt":
            return await self._get_meta_loader_version("quilt", mc_version)
        if loader == "forge":
            return await self.get_forge_version(mc_version)
        return None

    async def _get_meta_loader_version(
        self, loader: str, mc_version: str
    ) -> Optional[str]:
        """Fabric/Quilt meta API 风格: 数组首元素的 loader.version"""
        url = _LOADER_META_URLS[loader].format(mc_version=mc_version)
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    versions = await response.json()
                    if versions:
                        return versions[0]["loader"]["version"]
        except Exception:
            pass
        return None

    async def get_fabric_version(self, mc_version: str) -> Optional[str]:
        """获取 Fabric 加载器版本（旧方法名，保持兼容）"""
        return await self._get_meta_loader_version("fabric", mc_version)

    async def get_quilt_version(self, mc_version: str) -> Optional[str]:
        """获取 Quilt 加载器版本（旧方法名，保持兼容）"""
        return await self._get_meta_loader_version("quilt", mc_version)

    async def get_forge_version(self, mc_version: str) -> Optional[str]:
        """获取 Forge 加载器版本"""
        url = "https://files.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    versions = data.get(mc_version, [])
                    if versions:
                        return versions[-1]
        except Exception:
            pass
        return None

    async def close(self) -> None:
        """关闭客户端"""
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
