"""
向后兼容 shim — 数据模型已迁入 modfetch.domain

旧导入路径 from modfetch.models import X 继续可用（已弃用，将随主版本移除）。
"""

from modfetch.domain.config_models import (  # noqa: F401
    ConditionalEntry,
    ExtraUrl,
    FileType,
    MetadataConfig,
    MinecraftConfig,
    ModEntry,
    ModFetchConfig,
    ModLoader,
    MrpackMode,
    OutputConfig,
    OutputFormat,
    ParentConfig,
    PluginConfig,
)
from modfetch.domain.models import (  # noqa: F401
    DependencyInfo,
    FileInfo,
    ProjectInfo,
    ProjectType,
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
