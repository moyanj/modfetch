"""模组目录端口（Modrinth 等平台的抽象）"""

from typing import List, Optional, Protocol, Tuple

from modfetch.domain.models import ProjectInfo, VersionInfo


class CatalogPort(Protocol):
    """模组平台目录接口

    契约约定：所有查询方法在「找不到匹配项」时应返回空/None 而非抛异常；
    网络层错误（连接失败/超时/5xx）应抛出适配层异常交由上层统一处理。
    """

    async def get_project(self, identifier: str) -> Optional[ProjectInfo]:
        """按 ID 或 slug 获取项目信息，不存在返回 None

        实现期望：
            - identifier 为项目 ID 或 slug，二选一匹配即可
            - 找到返回完整 ProjectInfo；未找到返回 None
        """
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

        实现期望：
            - 依据 project_id + mc_version + loader 匹配可用版本；
              specific_version 非空时优先精确匹配指定版本号
            - file_info 为选中主文件（首个可用文件）的原始元数据，供下载端消费
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
        """搜索项目

        实现期望：
            - 返回按相关性排序的 ProjectInfo 列表，至多 limit 条
            - 无可匹配结果时返回空列表；过滤参数应作为与条件合并进查询
        """
        ...

    async def get_loader_version(
        self, loader: str, mc_version: str
    ) -> Optional[str]:
        """获取加载器在某个 MC 版本下的最新版本号

        实现期望：
            - 返回版本号字符串；平台无该组合版本时返回 None
        """
        ...

    async def close(self) -> None:
        """释放底层资源（连接池等）；实现必须可重复安全调用"""
        ...
