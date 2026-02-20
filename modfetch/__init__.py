"""
ModFetch - Minecraft 模组下载管理工具
"""

__version__ = "0.1.0"

# 初始化日志
from modfetch.logger import setup_logger

setup_logger()

# 导出主要组件
from modfetch.models import (
    ModFetchConfig,
    MinecraftConfig,
    OutputConfig,
    MetadataConfig,
)
from modfetch.orchestrator import ModFetchOrchestrator
from modfetch.exceptions import ModFetchError
from modfetch.logger import logger

__all__ = [
    "__version__",
    "ModFetchConfig",
    "MinecraftConfig",
    "OutputConfig",
    "MetadataConfig",
    "ModFetchOrchestrator",
    "ModFetchError",
    "logger",
]
