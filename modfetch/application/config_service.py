"""
配置服务（应用层）

统一配置边界: 解析 → 本地校验 → 远程校验。
消除 CLI 与 routes.py 中重复的三段式校验编排。
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
    """统一配置边界"""

    def parse(self, raw: Mapping[str, Any]) -> ModFetchConfig:
        """解析裸 Mapping → ModFetchConfig（不修改输入）"""
        try:
            return ModFetchConfig.from_dict(dict(raw))
        except ValueError as e:
            raise ConfigParseError(str(e)) from e

    def validate_local(self, config: ModFetchConfig) -> None:
        """本地校验: version/loader/条目完整性"""
        try:
            config.validate()
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    async def validate_remote(
        self, config: ModFetchConfig, catalog: CatalogPort
    ) -> ConfigValidationResult:
        """远程校验: 逐条目查平台，返回结构化报告（不抛异常）"""
        return await ProjectValidationService(catalog).validate_config(config)
