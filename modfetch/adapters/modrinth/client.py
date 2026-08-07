"""
Modrinth API 客户端

实现 CatalogPort。仅负责 HTTP 与 JSON 映射，不含业务流程。

错误转译约定：
- 404（资源不存在）→ 返回 None，由调用方按"未找到"处理
- 其余非 200 状态码 → 抛通用 APIError（携带 status_code/url 进 context）
- 领域层已定义 APINotFoundError/APIRateLimitError/APIServerError 等细分错误，
  当前统一走 APIError 以便调用方集中处理；如需按状态码细分可在此扩展。
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
    """Modrinth API 客户端（CatalogPort 实现）

    职责边界：只做 HTTP 请求与 JSON→领域模型映射，不参与
    版本匹配、依赖解析等业务逻辑（由 application 层负责）。
    测试中通过 monkeypatch 替换 ``_request``，故本类全部方法
    可离线验证，不依赖真实网络。
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        #: session 是否由本类创建：为 True 时 close() 才负责关闭，
        #: 外部注入的 session 生命周期由注入方管理，避免重复关闭。
        self._owned_session = session is None

    @property
    def session(self) -> aiohttp.ClientSession:
        """懒加载 aiohttp session（首次访问才创建）

        延迟到首次请求时才创建而非 __init__，使依赖方在只构造
        不使用的场景（如仅校验配置）下不产生连接池开销；且
        创建后复用同一个 session，以复用 TCP 连接与连接池。
        若外部 session 已被关闭则重建，避免复用已失效对象。
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(
        self, endpoint: str, params: Optional[dict] = None
    ) -> Optional[dict]:
        """发送 API 请求；404 返回 None，其他错误抛 APIError

        Args:
            endpoint: 完整请求 URL（含 base）
            params: 查询参数，将作为 query string 拼接

        Returns:
            200 时返回 JSON dict；404 时返回 None

        Raises:
            APIError: 非 200/404 状态码，context 中附带
                status_code 与 url 便于日志排查与用户提示。

        错误转译说明：404 被折叠为 None（"未找到"是一种正常
        业务结果而非异常），其余错误统一抛 APIError，由上层
        应用服务统一捕获处理。
        """
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
        """裸 GET 透传（供路由层代理 Modrinth API，返回 (status, json)）

        与 ``_request`` 不同：这里不抛异常、不做 404 折叠，
        把原始状态码原样返回，供 Web 路由层直接代理给前端
        （前端需要感知精确的 HTTP 语义）。
        """
        async with self.session.get(
            f"{MODRINTH_BASE_URL}{path}", params=params
        ) as response:
            if response.status == 200:
                return 200, await response.json()
            return response.status, None

    async def get_project(self, identifier: str) -> Optional[ProjectInfo]:
        """获取项目信息

        Args:
            identifier: 项目 ID 或 slug（Modrinth 两者皆可）

        Returns:
            项目存在时返回 ProjectInfo；不存在（404）返回 None
        """
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
        """搜索项目（CatalogPort）

        按 ports 协议命名的统一入口：参数名与端口定义对齐，
        内部转发给 ``search_projects``，仅做参数名适配。
        """
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
        """搜索项目（旧方法名，保持兼容）

        与 ``search`` 行为一致，保留旧调用方兼容。
        将过滤条件经 ``build_modrinth_facets`` 编码为 facets
        查询参数（Modrinth 搜索 API 的标准过滤语法）。
        """
        params = {
            "query": query,
            "limit": str(limit),
        }
        # 组装 facets：每个过滤条件作为独立 facet，Modrinth
        # 要求 facets 是 JSON 数组字符串，故需 dumps 后再放入 params。
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
        # hits 是搜索结果的条目列表，每项字段与 project 详情
        # 接口不同（如 project_id 而非 id），故用 map_search_hit。
        return [map_search_hit(item) for item in response.get("hits", [])]

    async def get_version(
        self,
        project_id: str,
        mc_version: str,
        loader: str,
        specific_version: Optional[str] = None,
    ) -> Tuple[Optional[VersionInfo], Optional[dict]]:
        """获取兼容的版本信息与主文件

        Args:
            project_id: 项目 ID 或 slug
            mc_version: Minecraft 版本号
            loader: 加载器名（fabric/forge/quilt/neoforge 等）
            specific_version: 精确版本 ID 或版本号；
                指定后仅在找到精确匹配时返回，不降级到最新版本

        Returns:
            (VersionInfo, file_info)；指定版本未找到时不降级到最新版本

        行为约定：
        - 无兼容版本（响应为空）→ (None, None)
        - 指定 specific_version 但未匹配 → (None, None)，
          刻意不降级到最新版，避免静默拿到错误版本
        - 未指定 → 取响应首元素（Modrinth 版本接口按
          日期倒序排列，首元素即最新兼容版本）
        """
        # game_versions/loaders 是 JSON 数组字符串，
        # Modrinth 约定用 JSON 数组文本作为查询参数。
        params = {"game_versions": f'["{mc_version}"]'}
        if loader:
            params["loaders"] = f'["{loader}"]'

        response = await self._request(
            f"{MODRINTH_BASE_URL}/project/{project_id}/version", params
        )

        if response is None or len(response) == 0:
            return None, None

        if specific_version:
            # 精确匹配：id 与 version_number 两种标识都接受，
            # 使调用方既可按内部 id 也可按人类可读版本号定位。
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
        """获取加载器版本（CatalogPort 统一入口）

        按加载器分发到不同数据源：
        - fabric/quilt → 各自官方 meta API（_get_meta_loader_version）
        - forge → Forge 官方 maven-metadata.json
        - 其他加载器 → None（暂无数据源）

        Returns:
            加载器版本号；获取失败或加载器不支持时返回 None
        """
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
        """Fabric/Quilt meta API 风格: 数组首元素的 loader.version

        meta API 返回按时间倒序的加载器版本数组，首元素即最新版。
        网络失败或响应异常时静默返回 None（加载器版本缺失属于
        可降级场景，不阻断整体构建，由调用方决定是否告警）。
        """
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
        """获取 Forge 加载器版本

        来源为 Forge 官方 maven-metadata.json（列出各 MC 版本
        对应的最新 Forge 构建号）。与 meta API 不同，此接口的
        键是 MC 版本，值为该版本的构建号列表，取末位即最新。
        失败时静默返回 None（与 _get_meta_loader_version 同样的
        可降级语义）。
        """
        url = "https://files.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    versions = data.get(mc_version, [])
                    if versions:
                        # 构建号列表按时间升序，末位为最新
                        return versions[-1]
        except Exception:
            pass
        return None

    async def close(self) -> None:
        """关闭客户端（仅关闭本类自建的 session）

        若 session 由外部注入（_owned_session=False），则生命周期
        归注入方所有，这里不做关闭，避免"关闭了别人的连接"。
        """
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
