import json
from typing import Optional

import aiofiles
import aiohttp
import toml

from modfetch.error import ModrinthError

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class Client:
    MODRINTH_BASE_URL = "https://api.modrinth.com/v2"

    def __init__(self):
        self.session = aiohttp.ClientSession()
        # self.project_id_to_slug_cache = {} # 这个缓存目前未使用，可以暂时移除

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
        """通过slug或id获取模组项目详情。"""
        # _request 已经处理了404，所以这里可以直接返回其结果
        a = await self._request(f"{self.MODRINTH_BASE_URL}/project/{idx}")
        if a["project_type"] == "mod":
            print(json.dumps(a))
            pass
        return a

    async def get_version(
        self,
        idx: str,
        mc_version: str,
        mod_loader: Optional[str] = None,
        specific_version: Optional[str] = None,
    ):
        """
        获取与指定Minecraft版本/模组加载器兼容的模组版本。
        如果指定 specific_version，则尝试查找该精确版本。
        返回 (version_data, primary_file_data)
        """
        params = {"game_versions": f'["{mc_version}"]'}
        if mod_loader:
            params["loaders"] = f'["{mod_loader}"]'
        versions = await self._request(
            f"{self.MODRINTH_BASE_URL}/project/{idx}/version", params
        )

        if not versions:
            # 如果没有找到版本，_request会返回None，或者get_project返回None时，这里就无版本列表
            return None, None

        if specific_version:
            for version in versions:
                if version["version_number"] == specific_version:
                    # 确保文件列表不为空
                    if version.get("files"):
                        return version, version["files"][0]
                    # else:
                    # print(f"  -> 找到指定版本 {specific_version} 但无可用文件。")
            return None, None  # 找不到指定版本或无文件

        else:
            # 返回最新版本（列表的第一个）的第一个文件
            if versions and versions[0].get("files"):
                return versions[0], versions[0]["files"][0]
            return None, None  # 没有可用版本或文件

    async def close(self):
        if not self.session.closed:
            await self.session.close()

    async def get_fabric_version(self, mc_version: str):
        """获取指定Minecraft版本下的Fabric版本。"""
        versions = await self._request(
            f"https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader/{mc_version}",
        )
        if versions:
            return versions[0]["loader"]["version"]

    async def get_quilt_version(self, mc_version: str):
        """获取指定Minecraft版本下的Quilt版本。"""
        versions = await self._request(
            f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}",
        )
        if versions:
            return versions[0]["loader"]["version"]

    async def get_forge_version(self, mc_version: str):
        """获取指定Minecraft版本下的Forge版本。"""
        versions = await self._request(
            f"https://bmclapi2.bangbang93.com/forge/minecraft/{mc_version}",
        )
        if versions:
            return versions[-1]["version"]

    async def get_config(self, url: str, format: str):
        if url.startswith("file://"):
            async with aiofiles.open(url[7:], "r") as f:
                text = await f.read()
        else:
            async with self.session.get(url) as response:
                text = await response.text()
        if format == "json":
            return json.loads(text)
        elif format == "yaml":
            if not HAS_YAML:
                raise ValueError("请安装 pyyaml")
            return yaml.safe_load(text)  # type: ignore
        elif format == "toml":
            return toml.loads(text)
