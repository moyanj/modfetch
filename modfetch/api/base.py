from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from modfetch.config import ModLoader


class ProjectType(Enum):
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
    versions: list[str]


@dataclass
class FileInfo:
    url: str
    filename: str
    size: int
    hashes: Optional[dict[str, str]] = None


@dataclass
class VersionInfo:
    """
    模组版本信息。
    """

    id: str
    name: str
    version: str
    loaders: list[ModLoader]
    game_versions: list[str]
    files: list[FileInfo]
    dependencies: list[str]

    @classmethod
    def from_modrinth(cls, data: dict) -> "VersionInfo":
        """
        将Modrinth API返回的版本信息转换为VersionInfo对象。
        """
        files = [
            FileInfo(
                url=file["url"],
                filename=file["filename"],
                size=file["size"],
                hashes=file["hashes"],
            )
            for file in data["files"]
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version_id"],
            files=files,
            loaders=[ModLoader(loader) for loader in data["loaders"]],
            game_versions=data["game_versions"],
            dependencies=data["dependencies"],
        )


class APIBase(ABC):
    @abstractmethod
    async def get_project(self, idx: str) -> Optional[ProjectInfo]:
        """
        通过idx获取模组项目详情。
        """
        pass

    @abstractmethod
    async def get_compatible_versions(
        self,
        idx: str,
        mc_version: str,
        mod_loader: str,
        specific_version: Optional[str] = None,
    ) -> Optional[VersionInfo]:
        """
        获取与指定模组兼容的Minecraft版本列表。
        """
        pass
