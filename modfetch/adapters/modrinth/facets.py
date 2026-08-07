"""Modrinth 搜索 facets 构造

将领域层的过滤条件（项目类型 / MC 版本 / 加载器）编码为
Modrinth 搜索 API 的 facets 查询参数。facets 是"与"关系的
过滤组，每组内是"或"关系；本工具每个条件单独成组，即
全部条件取"与"。
"""

import json
from typing import Optional


def build_modrinth_facets(
    *,
    project_type: Optional[str] = None,
    mc_version: Optional[str] = None,
    mod_loader: Optional[str] = None,
) -> Optional[str]:
    """构造 Modrinth 搜索 API 的 facets 参数

    Args:
        project_type: 项目类型（mod/resource_pack/shader 等）
        mc_version: Minecraft 版本号
        mod_loader: 加载器名（fabric/forge 等）

    Returns:
        编码后的 facets JSON 字符串；无任何过滤条件时返回 None
        （调用方据此省略该参数，避免传空 facets 干扰搜索）。

    字段前缀说明（Modrinth facet 语法）：
    - ``project_type:`` 过滤项目类型
    - ``versions:`` 过滤支持的 MC 版本
    - ``categories:`` 过滤加载器（加载器在 Modrinth 中归入 categories）
    """
    facets: list[list[str]] = []
    if project_type:
        facets.append([f"project_type:{project_type}"])
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    if mod_loader:
        facets.append([f"categories:{mod_loader}"])
    if not facets:
        return None
    # Modrinth 要求 facets 以 JSON 数组字符串形式作为查询参数
    return json.dumps(facets)
