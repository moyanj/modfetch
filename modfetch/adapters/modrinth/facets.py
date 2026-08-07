"""Modrinth 搜索 facets 构造"""

import json
from typing import Optional


def build_modrinth_facets(
    *,
    project_type: Optional[str] = None,
    mc_version: Optional[str] = None,
    mod_loader: Optional[str] = None,
) -> Optional[str]:
    """构造 Modrinth 搜索 API 的 facets 参数"""
    facets: list[list[str]] = []
    if project_type:
        facets.append([f"project_type:{project_type}"])
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    if mod_loader:
        facets.append([f"categories:{mod_loader}"])
    if not facets:
        return None
    return json.dumps(facets)
