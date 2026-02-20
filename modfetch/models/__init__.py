"""
ModFetch 数据模型包

包含配置模型和 API 模型定义。
"""

from modfetch.models.config import (
    ModLoader,
    OutputFormat,
    FileType,
    ConditionalEntry,
    ModEntry,
    ExtraUrl,
    ParentConfig,
    MinecraftConfig,
    OutputConfig,
    MetadataConfig,
    PluginConfig,
    ModFetchConfig,
    MrpackMode,
)
from modfetch.models.api import (
    ProjectType,
    ProjectInfo,
    FileInfo,
    DependencyInfo,
    VersionInfo,
)

__all__ = [
    # 配置模型
    "ModLoader",
    "OutputFormat",
    "FileType",
    "ConditionalEntry",
    "ModEntry",
    "ExtraUrl",
    "ParentConfig",
    "MinecraftConfig",
    "OutputConfig",
    "MetadataConfig",
    "PluginConfig",
    "ModFetchConfig",
    "MrpackMode",
    # API 模型
    "ProjectType",
    "ProjectInfo",
    "FileInfo",
    "DependencyInfo",
    "VersionInfo",
]
