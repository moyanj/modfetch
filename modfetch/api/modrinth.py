from typing import Optional
from modfetch.api.base import APIBase, FileInfo, ProjectType, ProjectInfo, VersionInfo
import aiohttp

from modfetch.error import ModrinthError

MODRINTH_BASE_URL = "https://api.modrinth.com/v2"


class ModrinthAPI(APIBase):

    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def _request(self, endpoint: str, params: Optional[dict] = None):
        async with self.session.get(endpoint, params=params) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                # 404不作为ModrinthError抛出，外部调用者可以据此判断资源不存在
                return None
            else:
                # 对于其他非200/404的状态码，抛出ModrinthError
                raise ModrinthError(
                    f"从 Modrinth API 获取数据失败 (状态码: {response.status}，URL: {response.url})",
                    response,
                )

    async def get_project(self, idx: str):
        response = await self._request(f"{MODRINTH_BASE_URL}/project/{idx}")
        if response is None:
            return None
        return ProjectInfo(
            id=response["id"],
            name=response["slug"],
            title=response["title"],
            description=response["description"],
            project_type=ProjectType(response["project_type"].upper()),
            versions=response["versions"],
        )

    async def get_compatible_versions(
        self,
        idx: str,
        mc_version: str,
        mod_loader: str,
        specific_version: Optional[str] = None,
    ) -> Optional[VersionInfo]:
        params = {"game_versions": f'["{mc_version}"]'}
        if mod_loader:
            params["loaders"] = f'["{mod_loader}"]'
        response = await self._request(
            f"{MODRINTH_BASE_URL}/project/{idx}/version", params
        )
        if response is None or len(response) == 0:
            return None
        if specific_version:
            for version in response:
                if version["id"] == specific_version:
                    if version["version_number"] == specific_version:
                        return VersionInfo.from_modrinth(version)
        version = response[0]
        return VersionInfo.from_modrinth(version)

    async def close(self):
        await self.session.close()
