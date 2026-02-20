"""
ModFetch 服务层

包含业务逻辑服务：API 客户端、模组解析、依赖处理、版本匹配。
"""

from modfetch.services.api_client import ModrinthClient
from modfetch.services.mod_resolver import ModResolver
from modfetch.services.dependency_resolver import DependencyResolver
from modfetch.services.version_matcher import VersionMatcher

__all__ = [
    "ModrinthClient",
    "ModResolver",
    "DependencyResolver",
    "VersionMatcher",
]
