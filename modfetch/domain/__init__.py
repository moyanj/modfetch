"""
领域层

纯领域模型与协议定义，零基础设施依赖（不导入 aiohttp/fastapi/click/loguru 等）。
"""

from modfetch.domain.models import (
    ProjectType,
    ProjectInfo,
    FileInfo,
    DependencyInfo,
    VersionInfo,
)
from modfetch.domain.config_models import (
    ModLoader,
    OutputFormat,
    MrpackMode,
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
)
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildError,
    BuildPlan,
    BuildResult,
    BuildStats,
    BuildTarget,
    OutputArtifact,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.events import BuildEvent, EventType
from modfetch.domain.errors import (
    ModFetchError,
    ConfigError,
    ConfigParseError,
    ConfigValidationError,
    APIError,
    APINotFoundError,
    APIRateLimitError,
    APIServerError,
    DownloadError,
    DownloadNetworkError,
    DownloadChecksumError,
    DownloadFileError,
    PackagerError,
    MrpackError,
    ZipError,
    ValidationError,
    ModrinthError,
)

__all__ = [
    # API 模型
    "ProjectType",
    "ProjectInfo",
    "FileInfo",
    "DependencyInfo",
    "VersionInfo",
    # 配置模型
    "ModLoader",
    "OutputFormat",
    "MrpackMode",
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
    # 构建计划
    "ArtifactCategory",
    "BuildError",
    "BuildPlan",
    "BuildResult",
    "BuildStats",
    "BuildTarget",
    "OutputArtifact",
    "OutputSpec",
    "ResolvedArtifact",
    # 事件
    "BuildEvent",
    "EventType",
    # 错误体系
    "ModFetchError",
    "ConfigError",
    "ConfigParseError",
    "ConfigValidationError",
    "APIError",
    "APINotFoundError",
    "APIRateLimitError",
    "APIServerError",
    "DownloadError",
    "DownloadNetworkError",
    "DownloadChecksumError",
    "DownloadFileError",
    "PackagerError",
    "MrpackError",
    "ZipError",
    "ValidationError",
    "ModrinthError",
]
