"""
ModFetch 插件系统

提供插件加载、管理和 Hook 机制。
"""

from modfetch.plugins.base import (
    HookType,
    HookContext,
    HookResult,
    ModFetchPlugin,
    PluginManager,
)
from modfetch.plugins.loader import PluginLoader, PluginLoadError

__all__ = [
    # 基础类型
    "HookType",
    "HookContext",
    "HookResult",
    "ModFetchPlugin",
    "PluginManager",
    # 加载器
    "PluginLoader",
    "PluginLoadError",
]
