"""
ModFetch - Minecraft 模组下载管理工具

包根：导入即初始化日志，并导出主要公共 API
（配置模型、构建服务、组合根、错误体系、logger）。
"""

__version__ = "1.0.0"

# 初始化日志
from modfetch.logger import setup_logger

setup_logger()

# 导出主要组件
from modfetch.domain import (
    ModFetchConfig,
    MinecraftConfig,
    OutputConfig,
    MetadataConfig,
)
from modfetch.application.build_service import BuildApplicationService
from modfetch.composition import create_build_service
from modfetch.domain.errors import ModFetchError
from modfetch.logger import logger

__all__ = [
    "__version__",
    "ModFetchConfig",
    "MinecraftConfig",
    "OutputConfig",
    "MetadataConfig",
    "BuildApplicationService",
    "create_build_service",
    "ModFetchError",
    "logger",
]
