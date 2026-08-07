"""
版本匹配器（自 services.version_matcher 迁移）

Minecraft 版本匹配、加载器版本匹配、版本范围处理。
依赖可选 CatalogPort（需统一加载器版本时传入）。
"""

from typing import List, Optional, Union

from loguru import logger

from modfetch.domain.config_models import ConditionalEntry, ModLoader
from modfetch.ports.catalog import CatalogPort


class VersionMatcher:
    """版本匹配器

    负责 Minecraft 版本匹配、配置条目过滤（only_version/feature）
    与加载器版本查询，供计划生成阶段筛选条目。
    """

    def __init__(self, catalog: Optional[CatalogPort] = None):
        self.catalog = catalog

    def matches(
        self,
        version: str,
        target_versions: Union[str, List[str]],
    ) -> bool:
        """检查版本是否匹配目标版本列表（支持单字符串或列表）

        当前为精确匹配：version 必须逐字命中 target_versions。
        """
        if isinstance(target_versions, str):
            target_versions = [target_versions]
        return version in target_versions

    def should_include(
        self,
        entry: Union[ConditionalEntry, dict, str],
        version: str,
        features: List[str],
    ) -> bool:
        """判断项目是否应包含在当前构建中

        支持 ConditionalEntry(ModEntry/ExtraUrl) 对象、dict 与字符串条目：
        - only_version: 版本命中指定列表才包含
        - feature: 启用条件——条目声明的 feature 全部被启用才包含；
          未声明 feature 的条目始终包含（与 ConditionalEntry 文档一致）

        注: 历史实现对 dict 条目采用"全部启用则排除"的反向语义，
        且对象条目(dataclass)从未命中 dict 分支导致过滤失效；本方法
        统一为启用条件语义并支持对象条目。
        """
        # 对象条目（ModEntry/ExtraUrl）与 dict 均提取条件字段；字符串无条件
        if isinstance(entry, ConditionalEntry):
            only_version = entry.only_version
            cfg_features = entry.feature
        elif isinstance(entry, dict):
            only_version = entry.get("only_version")
            cfg_features = entry.get("feature")
        else:
            return True

        # only_version: 版本不在指定列表 → 排除
        if only_version:
            versions = (
                [only_version]
                if isinstance(only_version, str)
                else list(only_version)
            )
            if version not in versions:
                logger.debug(
                    f"[过滤] 排除 {entry}: only_version={versions} 不含 {version}"
                )
                return False

        # feature: 启用条件——所有声明的功能标签都被启用才包含
        if cfg_features:
            feats = (
                [cfg_features]
                if isinstance(cfg_features, str)
                else list(cfg_features)
            )
            if not all(feature in features for feature in feats):
                logger.debug(
                    f"[过滤] 排除 {entry}: feature={feats} 未全部启用"
                )
                return False

        return True

    async def get_loader_version(
        self,
        loader: ModLoader,
        mc_version: str,
    ) -> Optional[str]:
        """获取模组加载器版本（统一走 CatalogPort）

        未注入 catalog 时返回 None，由调用方决定是否可选降级。
        """
        if not self.catalog:
            return None
        return await self.catalog.get_loader_version(loader.value, mc_version)