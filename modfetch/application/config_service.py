"""
配置服务（应用层）

统一配置边界: 解析 → 本地校验 → 远程校验。
消除 CLI 与 routes.py 中重复的三段式校验编排。

本地校验仅做结构完整性检查（不访问网络）；
远程校验返回结构化报告，由调用方决定如何处理。
"""

from typing import Any, List, Mapping, Optional, Union

from modfetch.application.validation import (
    ConfigValidationResult,
    ProjectValidationService,
)
from modfetch.application.version_matcher import VersionMatcher
from modfetch.domain.config_models import (
    SHADER_LOADER_SLUGS,
    ConditionalEntry,
    ModEntry,
    ModFetchConfig,
)
from modfetch.domain.errors import ConfigParseError, ConfigValidationError
from modfetch.ports.catalog import CatalogPort


def entry_identifier(entry: Union[str, ModEntry]) -> Optional[str]:
    """提取配置条目的 Modrinth 查询标识（字符串即 slug；ModEntry 优先 id）"""
    if isinstance(entry, str):
        return entry
    return entry.id or entry.slug


class ConfigService:
    """统一配置边界

    将裸 Mapping 解析为 ModFetchConfig，并承担本地/远程两级校验，
    供 CLI 与 Web 复用同一套校验编排。
    """

    def parse(self, raw: Mapping[str, Any]) -> ModFetchConfig:
        """解析裸 Mapping → ModFetchConfig（不修改输入）

        Args:
            raw: 配置来源的原始字典（TOML/YAML/JSON 解析产物）

        Returns:
            ModFetchConfig 数据类

        Raises:
            ConfigParseError: 字段缺失/类型错误等解析失败
        """
        try:
            return ModFetchConfig.from_dict(dict(raw))
        except ValueError as e:
            raise ConfigParseError(str(e)) from e

    def validate_local(
        self, config: ModFetchConfig, features: Optional[List[str]] = None
    ) -> None:
        """本地校验: version/loader/条目完整性 + 光影加载器关联（不访问网络）

        Args:
            config: 待校验配置
            features: 启用的功能标签；供 feature 条件编译判断。
                省略时使用 ``config.features``。注意 CLI 的 ``-f`` 值在
                覆盖 ``config.features`` 前并未写入配置，调用方应显式传入。

        Raises:
            ConfigValidationError: 配置结构不完整/非法，或光影包缺加载器
        """
        try:
            config.validate()
            self._validate_shader_loader(
                config, features if features is not None else config.features
            )
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    @staticmethod
    def _validate_shader_loader(
        config: ModFetchConfig, features: List[str]
    ) -> None:
        """跨字段关联校验: 有实际参与的光影包 → mods 必须含光影加载器

        光影包（如 Complementary / BSL）必须配合光影加载器（iris/oculus/
        optifine）才能生效。按 Minecraft 版本粒度判断：仅当某版本下经
        feature/only_version 过滤后仍有实际参与的光影包时，才要求该版本
        的 mods 中存在光影加载器（加载器本身同样需通过条件过滤）。

        Raises:
            ValueError: 某版本含光影包但缺少对应的光影加载器
        """
        matcher = VersionMatcher()
        for version in config.minecraft.version:
            active_shaders = [
                s
                for s in config.minecraft.shaderpacks
                if matcher.should_include(s, version, features)
            ]
            if not active_shaders:
                continue
            # 该版本有实际参与的光影包，要求 mods 含等于的光影加载器
            has_loader = any(
                (entry_identifier(m) or "").lower() in SHADER_LOADER_SLUGS
                and matcher.should_include(m, version, features)
                for m in config.minecraft.mods
            )
            if not has_loader:
                raise ValueError(
                    f"Minecraft {version} 配置了光影包 "
                    f"{', '.join(str(s) for s in active_shaders)}，"
                    f"mods 必须包含光影加载器 "
                    f"({'/'.join(SHADER_LOADER_SLUGS)})"
                )

    async def validate_remote(
        self, config: ModFetchConfig, catalog: CatalogPort
    ) -> ConfigValidationResult:
        """远程校验: 逐条目查平台，返回结构化报告（不抛异常）

        Args:
            config: 待校验配置
            catalog: 目录端口（Modrinth 等平台实现）

        Returns:
            ConfigValidationResult: valid/issues，调用方据 issues 自行处理
        """
        return await ProjectValidationService(catalog).validate_config(config)
