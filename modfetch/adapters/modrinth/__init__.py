"""Modrinth 平台适配器

对 Modrinth API 的 HTTP 访问封装：客户端（含错误转译与
session 管理）、搜索结果映射、搜索 facets 构造。
对外统一导出这三个能力，供 application 层与 Web 路由层使用。
"""

from modfetch.adapters.modrinth.client import ModrinthClient, MODRINTH_BASE_URL
from modfetch.adapters.modrinth.facets import build_modrinth_facets

__all__ = ["ModrinthClient", "MODRINTH_BASE_URL", "build_modrinth_facets"]
