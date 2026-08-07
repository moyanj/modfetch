"""
Modrinth JSON → 领域模型映射

职责：把 Modrinth API 返回的原始 JSON 结构翻译为领域模型
（ProjectInfo/VersionInfo），隔离 API 字段名与领域字段名的差异。
所有函数为纯函数（无 IO、无状态），便于单测与复用。

字段映射要点：
- Modrinth 的 ``id`` 字段是 UUID，``slug`` 才是人类可读的短名；
  领域模型的 ``name`` 保存 slug（因为配置里用 slug 引用模组）。
- 搜索接口的 hit 与详情接口字段不同（project_id vs id）。
"""

from typing import Optional

from modfetch.domain.models import ProjectInfo, VersionInfo


def map_project(data: dict) -> ProjectInfo:
    """Modrinth project 详情响应 → ProjectInfo

    详情接口字段齐全，直接取 key（缺字段会抛 KeyError，让
    调用方尽早感知 API 结构变化，而非静默填充空值）。
    """
    return ProjectInfo(
        id=data["id"],  # Modrinth 内部 UUID，用于后续 API 定位
        name=data["slug"],  # slug 是稳定短名，配置层用它引用模组
        title=data["title"],
        description=data["description"],
        project_type=data["project_type"],
        versions=data["versions"],  # 该项目所有版本 id 列表
    )


def map_search_hit(item: dict) -> ProjectInfo:
    """Modrinth search hit → ProjectInfo（附带 downloads 属性）

    与 ``map_project`` 的差异：搜索接口的每条 hit 字段精简且命名
    不同（如 ``project_id`` 而非 ``id``、无 ``versions`` 列表），
    故统一用 ``get`` 取默认值，避免缺字段时整个搜索失败。
    额外把 ``downloads``（下载量，用于排序/展示）动态附加到模型上——
    领域模型没有该字段，因此用 ``setattr`` 而不是修改 dataclass。
    """
    project = ProjectInfo(
        id=item.get("project_id", ""),
        name=item.get("slug", ""),
        title=item.get("title", ""),
        description=item.get("description", ""),
        project_type=item.get("project_type", ""),
        versions=[],  # 搜索响应不含版本列表，置空
    )
    # 下载量不在 ProjectInfo 定义中，动态扩展避免改动领域模型
    setattr(project, "downloads", int(item.get("downloads", 0)))
    return project


def map_version(data: dict) -> VersionInfo:
    """Modrinth version 响应 → VersionInfo

    字段级映射（files/dependencies/loaders 的解析）在
    ``VersionInfo.from_modrinth`` 中实现，这里仅作转发，
    保持 client 层只依赖 mapper 的单一入口。
    """
    return VersionInfo.from_modrinth(data)


def pick_primary_file(version: dict) -> Optional[dict]:
    """从版本响应中选取主文件（优先 primary，否则第一个）

    Modrinth 一个版本可挂多个文件（不同平台/功能分支），但
    打包时只需一个主文件：优先取显式标记 ``primary`` 的文件，
    无标记时退化为取第一个（顺序即 API 返回顺序）。
    无文件时返回 None，由调用方按"该版本无可用文件"处理。
    """
    files = version.get("files", [])
    if not files:
        return None
    for file in files:
        if file.get("primary", False):
            return file
    return files[0]
