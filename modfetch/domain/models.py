"""
API 领域模型

定义项目信息、版本信息等领域数据结构（零基础设施依赖）。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from modfetch.domain.config_models import ModLoader


class ProjectType(Enum):
    """项目类型（对应 Modrinth 的 project_type 字段）"""

    #: 模组
    MOD = "mod"
    #: 资源包
    RESOURCE_PACK = "resource_pack"
    #: 光影包
    SHADER = "shader"
    #: 数据包
    DATAPACK = "datapack"


@dataclass
class ProjectInfo:
    """模组项目信息（Modrinth 项目摘要，不含完整版本明细）"""

    id: str  #: Modrinth 项目 ID
    name: str  #: 项目 slug（URL 中的唯一标识，非显示名）
    title: str  #: 显示标题
    description: str  #: 项目简介
    project_type: ProjectType  #: 项目类别
    versions: List[str] = field(default_factory=list)  #: 可用版本号列表


@dataclass
class FileInfo:
    """版本文件信息"""

    url: str  #: 文件下载地址
    filename: str  #: 文件名
    size: int  #: 文件大小（字节）
    #: 校验哈希，形如 {"sha1": "...", "sha512": "..."}
    hashes: Optional[Dict[str, str]] = None


@dataclass
class DependencyInfo:
    """模组依赖信息"""

    project_id: str  #: 被依赖项目的 ID
    dependency_type: str  #: 依赖类型：required / optional / incompatible / embedded


@dataclass
class VersionInfo:
    """模组版本信息（某个项目在特定加载器/MC 版本下的版本）"""

    id: str  #: Modrinth 版本 ID
    name: str  #: 版本标题
    version: str  #: 版本号（version_number）
    loaders: List[ModLoader]  #: 该版本支持的加载器
    game_versions: List[str]  #: 该版本支持的 Minecraft 版本
    files: List[FileInfo] = field(default_factory=list)  #: 版本文件列表
    dependencies: List[DependencyInfo] = field(default_factory=list)  #: 依赖列表

    @classmethod
    def from_modrinth(cls, data: dict) -> "VersionInfo":
        """将 Modrinth API 返回的版本数据转换为 VersionInfo"""
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
            loaders=[ModLoader(loader) for loader in data.get("loaders", [])],
            game_versions=data.get("game_versions", []),
            dependencies=dependencies,
        )
