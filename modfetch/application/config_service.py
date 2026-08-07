"""
配置服务（应用层）

统一配置边界: 解析 → 本地校验 → 远程校验。
消除 CLI 与 routes.py 中重复的三段式校验编排。

本地校验仅做结构完整性检查（不访问网络）；
远程校验返回结构化报告，由调用方决定如何处理。
"""

from typing import Any, Mapping

from modfetch.application.validation import (
    ConfigValidationResult,
    ProjectValidationService,
)
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import ConfigParseError, ConfigValidationError
from modfetch.ports.catalog import CatalogPort


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

    def validate_local(self, config: ModFetchConfig) -> None:
        """本地校验: version/loader/条目完整性（不访问网络）

        Raises:
            ConfigValidationError: 配置结构不完整或非法
        """
        try:
            config.validate()
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

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
