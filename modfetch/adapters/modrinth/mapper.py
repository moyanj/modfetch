"""Modrinth JSON → 领域模型映射"""

from typing import Optional

from modfetch.domain.models import ProjectInfo, VersionInfo


def map_project(data: dict) -> ProjectInfo:
    """Modrinth project 响应 → ProjectInfo"""
    return ProjectInfo(
        id=data["id"],
        name=data["slug"],
        title=data["title"],
        description=data["description"],
        project_type=data["project_type"],
        versions=data["versions"],
    )


def map_search_hit(item: dict) -> ProjectInfo:
    """Modrinth search hit → ProjectInfo（附带 downloads 属性）"""
    project = ProjectInfo(
        id=item.get("project_id", ""),
        name=item.get("slug", ""),
        title=item.get("title", ""),
        description=item.get("description", ""),
        project_type=item.get("project_type", ""),
        versions=[],
    )
    setattr(project, "downloads", int(item.get("downloads", 0)))
    return project


def map_version(data: dict) -> VersionInfo:
    """Modrinth version 响应 → VersionInfo"""
    return VersionInfo.from_modrinth(data)


def pick_primary_file(version: dict) -> Optional[dict]:
    """从版本响应中选取主文件（优先 primary，否则第一个）"""
    files = version.get("files", [])
    if not files:
        return None
    for file in files:
        if file.get("primary", False):
            return file
    return files[0]
