"""
API 数据模型

定义 API 相关的数据类，包括项目信息、版本信息等。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict

from modfetch.models.config import (
    ModLoader,
    ConditionalEntry,
    ModEntry,
    ExtraUrl,
    ConditionalEntry,
    ModEntry,
    ExtraUrl,
)


class ProjectType(Enum):
    """项目类型"""

    MOD = "mod"
    RESOURCE_PACK = "resource_pack"
    SHADER = "shader"
    DATAPACK = "datapack"


@dataclass
class ProjectInfo:
    """
    模组项目信息。
    """

    id: str
    name: str
    title: str
    description: str
    project_type: ProjectType
    versions: List[str]


@dataclass
class FileInfo:
    """文件信息"""

    url: str
    filename: str
    size: int
    hashes: Optional[Dict[str, str]] = None


@dataclass
class DependencyInfo:
    """依赖信息"""

    project_id: str
    dependency_type: str  # required, optional, incompatible, embedded


@dataclass
class VersionInfo:
    """
    模组版本信息。
    """

    id: str
    name: str
    version: str
    loaders: List[ModLoader]
    game_versions: List[str]
    files: List[FileInfo]
    dependencies: List[DependencyInfo]

    @classmethod
    def from_modrinth(cls, data: dict) -> "VersionInfo":
        """
        将 Modrinth API 返回的版本信息转换为 VersionInfo 对象。
        """
        files = [
            FileInfo(
                url=file["url"],
                filename=file["filename"],
                size=file["size"],
                hashes=file.get("hashes"),
            )
            for file in data.get("files", [])
        ]

        dependencies = [
            DependencyInfo(
                project_id=dep.get("project_id", ""),
                dependency_type=dep.get("dependency_type", "required"),
            )
            for dep in data.get("dependencies", [])
        ]

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version_number", ""),
            files=files,
            loaders=[ModLoader(loader) for loader in data.get("loaders", [])],
            game_versions=data.get("game_versions", []),
            dependencies=dependencies,
        )
