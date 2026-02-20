"""
API 客户端抽象

提供统一的 API 客户端接口，支持 Modrinth 等平台。
"""

from typing import Optional
import aiohttp

from modfetch.models import ProjectInfo, VersionInfo
from modfetch.exceptions import APIError, APINotFoundError


MODRINTH_BASE_URL = "https://api.modrinth.com/v2"


class ModrinthClient:
    """Modrinth API 客户端"""

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
        """发送 API 请求"""
        async with self.session.get(endpoint, params=params) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return None
            else:
                raise APIError(
                    f"API 请求失败 (状态码: {response.status})",
                    response=response,
                )

    async def get_project(self, idx: str) -> Optional[ProjectInfo]:
        """获取项目信息"""
        response = await self._request(f"{MODRINTH_BASE_URL}/project/{idx}")
        if response is None:
            return None
        return ProjectInfo(
            id=response["id"],
            name=response["slug"],
            title=response["title"],
            description=response["description"],
            project_type=response["project_type"],
            versions=response["versions"],
        )

    async def get_version(
        self,
        idx: str,
        mc_version: str,
        mod_loader: str,
        specific_version: Optional[str] = None,
    ) -> tuple[Optional[VersionInfo], Optional[dict]]:
        """
        获取兼容的版本信息

        Returns:
            tuple: (VersionInfo, file_info)
        """
        params = {"game_versions": f'["{mc_version}"]'}
        if mod_loader:
            params["loaders"] = f'["{mod_loader}"]'

        response = await self._request(
            f"{MODRINTH_BASE_URL}/project/{idx}/version", params
        )

        if response is None or len(response) == 0:
            return None, None

        if specific_version:
            for version in response:
                if (
                    version["id"] == specific_version
                    or version["version_number"] == specific_version
                ):
                    version_info = VersionInfo.from_modrinth(version)
                    primary_file = self._get_primary_file(version)
                    return version_info, primary_file

        # 返回第一个版本
        version = response[0]
        version_info = VersionInfo.from_modrinth(version)
        primary_file = self._get_primary_file(version)
        return version_info, primary_file

    def _get_primary_file(self, version: dict) -> Optional[dict]:
        """获取主文件信息"""
        files = version.get("files", [])
        if not files:
            return None

        # 优先选择 primary 文件
        for file in files:
            if file.get("primary", False):
                return file

        # 否则返回第一个文件
        return files[0]

    async def get_fabric_version(self, mc_version: str) -> Optional[str]:
        """获取 Fabric 加载器版本"""
        url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    versions = await response.json()
                    if versions:
                        return versions[0]["loader"]["version"]
        except Exception:
            pass
        return None

    async def get_quilt_version(self, mc_version: str) -> Optional[str]:
        """获取 Quilt 加载器版本"""
        url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    versions = await response.json()
                    if versions:
                        return versions[0]["loader"]["version"]
        except Exception:
            pass
        return None

    async def get_forge_version(self, mc_version: str) -> Optional[str]:
        """获取 Forge 加载器版本"""
        url = f"https://files.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    versions = data.get(mc_version, [])
                    if versions:
                        return versions[-1]  # 返回最新版本
        except Exception:
            pass
        return None

    async def close(self):
        """关闭客户端"""
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
