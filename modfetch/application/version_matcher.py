"""
版本匹配器（自 services.version_matcher 迁移）

Minecraft 版本匹配、加载器版本匹配、版本范围处理。
依赖可选 CatalogPort（需统一加载器版本时传入）。
"""

from typing import List, Optional, Union

from modfetch.domain.config_models import ModLoader
from modfetch.ports.catalog import CatalogPort


class VersionMatcher:
    """版本匹配器"""

    def __init__(self, catalog: Optional[CatalogPort] = None):
        self.catalog = catalog

    def matches(
        self,
        version: str,
        target_versions: Union[str, List[str]],
    ) -> bool:
        """检查版本是否匹配目标版本列表"""
        if isinstance(target_versions, str):
            target_versions = [target_versions]
        return version in target_versions

    def should_include(
        self,
        entry: Union[dict, str],
        version: str,
        features: List[str],
    ) -> bool:
        """判断项目是否应包含在当前构建中

        注: 仅 dict 条目参与 only_version/feature 过滤；
        对象条目（ModEntry 等）按现有行为视为始终包含。
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
        """获取模组加载器版本（统一走 CatalogPort）"""
        if not self.catalog:
            return None
        return await self.catalog.get_loader_version(loader.value, mc_version)