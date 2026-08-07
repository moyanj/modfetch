"""向后兼容 shim — API 数据类已迁入 modfetch.domain.models"""

from modfetch.domain.models import (  # noqa: F401
    DependencyInfo,
    FileInfo,
    ProjectInfo,
    ProjectType,
    VersionInfo,
)

__all__ = [
    "ProjectType",
    "ProjectInfo",
    "FileInfo",
    "DependencyInfo",
    "VersionInfo",
]
