"""
版本匹配服务

实现 Minecraft 版本匹配、模组加载器版本匹配、版本范围处理。
"""

from typing import Union, List, Optional

from modfetch.models import ModLoader
from modfetch.services.api_client import ModrinthClient


class VersionMatcher:
    """版本匹配器"""

    def __init__(self, client: Optional[ModrinthClient] = None):
        self.client = client

    def matches(
        self,
        version: str,
        target_versions: Union[str, List[str]],
    ) -> bool:
        """
        检查版本是否匹配目标版本列表

        Args:
            version: 要检查的版本
            target_versions: 目标版本或版本列表

        Returns:
            是否匹配
        """
        if isinstance(target_versions, str):
            target_versions = [target_versions]

        return version in target_versions

    def should_include(
        self,
        entry: Union[dict, str],
        version: str,
        features: List[str],
    ) -> bool:
        """
        判断项目是否应包含在当前构建中

        Args:
            entry: 配置项（字典或字符串）
            version: 当前版本
            features: 启用的功能列表

        Returns:
            是否包含
        """
        if isinstance(entry, dict):
            # 检查 only_version
            if need_versions := entry.get("only_version"):
                if isinstance(need_versions, str):
                    need_versions = [need_versions]
                if version not in need_versions:
                    return False

            # 检查 feature
            if cfg_features := entry.get("feature"):
                if isinstance(cfg_features, str):
                    cfg_features = [cfg_features]
                # 如果所有功能都启用，则排除
                if all(feature in features for feature in cfg_features):
                    return False

        return True

    async def get_loader_version(
        self,
        loader: ModLoader,
        mc_version: str,
    ) -> Optional[str]:
        """
        获取模组加载器版本

        Args:
            loader: 加载器类型
            mc_version: Minecraft 版本

        Returns:
            加载器版本或 None
        """
        if not self.client:
            return None

        if loader == ModLoader.FABRIC:
            return await self.client.get_fabric_version(mc_version)
        elif loader == ModLoader.QUILT:
            return await self.client.get_quilt_version(mc_version)
        elif loader == ModLoader.FORGE:
            return await self.client.get_forge_version(mc_version)

        return None
