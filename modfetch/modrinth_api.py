from typing import Optional
import aiohttp

from modfetch.error import ModrinthError


class ModrinthClient:
    BASE_URL = "https://api.modrinth.com/v2"

    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.project_id_to_slug_cache = {}

    async def _request(
        self, endpoint: str, params: Optional[dict] = None
    ) -> dict | None:
        async with self.session.get(
            self.BASE_URL + endpoint, params=params
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise ModrinthError(f"Failed to fetch from Modrinth API", response)

    async def get_project(self, idx: str):
        """通过slug或id获取模组项目详情。"""
        try:
            return await self._request(f"/project/{idx}")
        except ModrinthError as e:
            if e.response.status == 404:
                return None
            raise e

    async def get_version(
        self,
        idx: str,
        mc_version: str,
        mod_loader: str,
        specific_version: Optional[str] = None,
    ) -> tuple[dict | None, dict | None]:
        """
        获取与指定Minecraft版本/模组加载器兼容的模组版本。
        如果指定 specific_version，则尝试查找该精确版本。
        返回 (version_data, primary_file_data)
        """
        print(
            f"-> 正在查找兼容版本 (项目ID: {idx}, MC: {mc_version}, 加载器: {mod_loader}, 指定版本: {specific_version or '最新'})..."
        )

        params = {"game_versions": f'["{mc_version}"]', "loaders": f'["{mod_loader}"]'}
        try:
            versions = await self._request(f"/project/{idx}/version", params)
        except ModrinthError as e:
            if e.response.status == 404:
                return None, None
            raise e
        if not versions:
            print("  -> 找不到兼容的版本")
            exit(1)
            return None, None

        if specific_version:
            for version in versions:
                if version["version_number"] == specific_version:
                    return version, version["files"][0]
            print(f"  -> 找不到指定版本 {specific_version}")
            exit(1)
            return None, None
        else:
            return versions[0], versions[0]["files"][0]

    async def close(self):
        await self.session.close()
