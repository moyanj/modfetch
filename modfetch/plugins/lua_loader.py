"""
Lua 插件加载器

支持从本地文件或远程 URL 加载 Lua 插件。
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import aiohttp

from modfetch.plugins.base import PluginManager
from modfetch.plugins.lua_runtime import (
    LuaPluginError,
    LuaPluginWrapper,
    LuaRuntimeManager,
)
from modfetch.services import ModrinthClient
from modfetch.models import ModFetchConfig

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("modfetch")


class LuaPluginLoader:
    """
    Lua 插件加载器

    负责加载和管理 Lua 插件。
    """

    def __init__(
        self,
        plugin_manager: PluginManager,
        modrinth_client: Optional[ModrinthClient] = None,
        config: Optional[ModFetchConfig] = None,
    ):
        self.plugin_manager = plugin_manager
        self._modrinth_client = modrinth_client
        self._config = config
        self._runtime = LuaRuntimeManager(
            modrinth_client=modrinth_client,
            config=config,
        )
        self._loaded_plugins: Dict[str, LuaPluginWrapper] = {}

    async def initialize(self) -> None:
        """初始化 Lua 运行时"""
        self._runtime.initialize()
        logger.debug("Lua 插件加载器已初始化")

    async def shutdown(self) -> None:
        """关闭 Lua 运行时"""
        for name, plugin in self._loaded_plugins.items():
            await plugin.shutdown()
        self._runtime.shutdown()
        logger.debug("Lua 插件加载器已关闭")

    async def load_from_path(
        self, path: Union[str, Path], config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从路径加载 Lua 插件

        Args:
            path: 插件路径（文件或 URL）
            config: 插件配置

        Returns:
            bool: 是否加载成功
        """
        path_str = str(path)

        if path_str.startswith("http://") or path_str.startswith("https://"):
            return await self._load_from_url(path_str, config)
        elif os.path.isfile(path_str):
            return await self._load_from_file(path_str, config)
        else:
            logger.error(f"不支持的 Lua 插件路径: {path_str}")
            return False

    async def load_multiple(
        self, paths: List[str], configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, bool]:
        """
        批量加载 Lua 插件

        Args:
            paths: 插件路径列表
            configs: 插件配置字典

        Returns:
            Dict[str, bool]: 每个路径的加载结果
        """
        results = {}
        configs = configs or {}

        for path in paths:
            config = configs.get(path, {})
            try:
                results[path] = await self.load_from_path(path, config)
            except Exception as e:
                logger.error(f"加载 Lua 插件 {path} 失败: {e}")
                results[path] = False

        return results

    async def _load_from_file(
        self, file_path: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """从文件加载 Lua 插件"""
        path = Path(file_path)

        if not path.exists():
            logger.error(f"Lua 插件文件不存在: {file_path}")
            return False

        if path.suffix != ".lua":
            logger.error(f"不支持的文件格式: {path.suffix}，期望 .lua")
            return False

        # 创建新的运行时实例（每个插件独立，共享客户端和配置）
        runtime = LuaRuntimeManager(
            modrinth_client=self._modrinth_client,
            config=self._config,
        )
        runtime.initialize()

        # 创建插件包装器
        plugin_name = path.stem
        wrapper = LuaPluginWrapper(plugin_name, runtime)

        try:
            if wrapper.load_from_file(path):
                # 初始化插件
                await wrapper.initialize(config or {})

                # 注册到插件管理器
                if self.plugin_manager.register_plugin(wrapper, config):
                    self._loaded_plugins[plugin_name] = wrapper
                    return True
                else:
                    await wrapper.shutdown()
                    return False
            else:
                runtime.shutdown()
                return False

        except Exception as e:
            logger.error(f"加载 Lua 插件 {file_path} 失败: {e}")
            runtime.shutdown()
            return False

    async def _load_from_url(
        self, url: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """从 URL 加载 Lua 插件"""
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            logger.error(f"不支持的 URL 协议: {parsed.scheme}")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"无法下载插件: HTTP {response.status}")
                        return False

                    source = await response.text()

        except aiohttp.ClientError as e:
            logger.error(f"下载插件失败: {e}")
            return False

        # 创建临时文件
        filename = Path(parsed.path).name or "plugin.lua"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write(source)
            temp_path = f.name

        try:
            return await self._load_from_file(temp_path, config)
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def scan_directory(self, directory: str) -> List[str]:
        """
        扫描目录中的所有 Lua 插件

        Args:
            directory: 要扫描的目录

        Returns:
            List[str]: Lua 插件路径列表
        """
        path = Path(directory)
        if not path.exists():
            return []

        plugin_paths = []

        # 查找所有 .lua 文件
        for lua_file in path.rglob("*.lua"):
            # 跳过隐藏文件和测试文件
            if lua_file.name.startswith(".") or lua_file.name.startswith("test_"):
                continue
            plugin_paths.append(str(lua_file))

        return plugin_paths

    async def unload_plugin(self, name: str) -> bool:
        """
        卸载 Lua 插件

        Args:
            name: 插件名称

        Returns:
            bool: 是否卸载成功
        """
        if name not in self._loaded_plugins:
            logger.warning(f"Lua 插件 {name} 未加载")
            return False

        wrapper = self._loaded_plugins[name]

        # 从插件管理器注销
        self.plugin_manager.unregister_plugin(name)

        # 关闭插件
        await wrapper.shutdown()

        # 移除记录
        del self._loaded_plugins[name]

        logger.info(f"Lua 插件 {name} 已卸载")
        return True

    def list_loaded(self) -> List[Dict[str, Any]]:
        """
        列出所有已加载的 Lua 插件

        Returns:
            List[Dict[str, Any]]: 插件信息列表
        """
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "author": p.author,
                "enabled": p.enabled,
            }
            for p in self._loaded_plugins.values()
        ]
