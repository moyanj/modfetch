"""
依赖处理服务

实现依赖图构建、依赖去重、循环依赖检测。
"""

from typing import Set, List

from modfetch.models import ProjectInfo, VersionInfo
from modfetch.services.api_client import ModrinthClient


class DependencyResolver:
    """依赖解析器"""

    def __init__(self, client: ModrinthClient):
        self.client = client
        self._processed: Set[str] = set()
        self._dependencies: List[tuple[ProjectInfo, VersionInfo, dict]] = []

    async def resolve(
        self,
        version_info: VersionInfo,
        mc_version: str,
        mod_loader: str,
    ) -> List[tuple[ProjectInfo, VersionInfo, dict]]:
        """
        解析依赖

        Args:
            version_info: 版本信息
            mc_version: Minecraft 版本
            mod_loader: 模组加载器

        Returns:
            依赖列表 (project_info, version_info, file_info)
        """
        self._processed.clear()
        self._dependencies.clear()

        await self._resolve_recursive(version_info, mc_version, mod_loader)

        return self._dependencies

    async def _resolve_recursive(
        self,
        version_info: VersionInfo,
        mc_version: str,
        mod_loader: str,
    ):
        """递归解析依赖"""
        for dep in version_info.dependencies:
            dep_type = dep.dependency_type
            dep_id = dep.project_id

            if dep_type != "required":
                continue

            if dep_id in self._processed:
                continue

            self._processed.add(dep_id)

            # 获取依赖项目信息
            dep_info = await self.client.get_project(dep_id)
            if not dep_info:
                continue

            # 获取依赖版本信息
            dep_version, dep_file = await self.client.get_version(
                dep_id, mc_version, mod_loader
            )

            if dep_version and dep_file:
                self._dependencies.append((dep_info, dep_version, dep_file))
                # 递归解析依赖的依赖
                await self._resolve_recursive(dep_version, mc_version, mod_loader)

    def clear_cache(self):
        """清除缓存"""
        self._processed.clear()
        self._dependencies.clear()
