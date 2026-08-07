"""模组目录端口（Modrinth 等平台的抽象）"""

from typing import List, Optional, Protocol, Tuple

from modfetch.domain.models import ProjectInfo, VersionInfo


class CatalogPort(Protocol):
    """模组平台目录接口"""

    async def get_project(self, identifier: str) -> Optional[ProjectInfo]:
        """按 ID 或 slug 获取项目信息，不存在返回 None"""
        ...

    async def get_version(
        self,
        project_id: str,
        mc_version: str,
        loader: str,
        specific_version: Optional[str] = None,
    ) -> Tuple[Optional[VersionInfo], Optional[dict]]:
        """获取兼容版本与主文件信息

        Returns:
            (VersionInfo, file_info dict)；任一不存在则 (None, None)
        """
        ...

    async def search(
        self,
        query: str,
        *,
        project_type: Optional[str] = None,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 5,
    ) -> List[ProjectInfo]:
        """搜索项目"""
        ...

    async def get_loader_version(
        self, loader: str, mc_version: str
    ) -> Optional[str]:
        """获取加载器在某个 MC 版本下的最新版本号"""
        ...

    async def close(self) -> None:
        """释放底层资源"""
        ...
