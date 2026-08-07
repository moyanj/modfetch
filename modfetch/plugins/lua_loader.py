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
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.domain.config_models import ModFetchConfig

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("modfetch")


class LuaPluginLoader:
    """
    Lua 插件加载器

    负责 Lua 插件的发现、加载与注册（与 PluginLoader 对应，按 .lua 后缀分发）。
    每个 Lua 插件在加载时都会创建独立的 LuaRuntimeManager 实例（共享 ModrinthClient
    与配置），并通过 LuaPluginWrapper 适配成 ModFetchPlugin 接口后注册进 PluginManager。
    使用前必须先 await initialize() 启动运行时，结束时 await shutdown() 释放。
    """

    def __init__(
        self,
        plugin_manager: PluginManager,
        modrinth_client: Optional[ModrinthClient] = None,
        config: Optional[ModFetchConfig] = None,
    ):
        """
        初始化 Lua 插件加载器

        Args:
            plugin_manager: 插件管理器（Lua 插件最终注册到这里）
            modrinth_client: 可选，注入给 Lua 运行时以暴露 Modrinth API
            config: 可选，注入给 Lua 运行时以暴露配置 API
        """
        self.plugin_manager = plugin_manager
        self._modrinth_client = modrinth_client
        self._config = config
        # 加载器级运行时：用于 initialize/shutdown 的全局生命周期管理
        self._runtime = LuaRuntimeManager(
            modrinth_client=modrinth_client,
            config=config,
        )
        # 已加载的 Lua 插件包装器，key 为插件名
        self._loaded_plugins: Dict[str, LuaPluginWrapper] = {}

    async def initialize(self) -> None:
        """初始化 Lua 运行时（加载器级运行时，供全局环境准备）"""
        self._runtime.initialize()
        logger.debug("Lua 插件加载器已初始化")

    async def shutdown(self) -> None:
        """关闭 Lua 运行时：先逐个关闭已加载插件，再释放加载器级运行时"""
        for name, plugin in self._loaded_plugins.items():
            await plugin.shutdown()
        self._runtime.shutdown()
        logger.debug("Lua 插件加载器已关闭")

    async def load_from_path(
        self, path: Union[str, Path], config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从路径加载 Lua 插件

        按输入自动分派：URL → _load_from_url；现有文件 → _load_from_file；
        其余路径视为不支持并记录错误。

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

        逐个调用 load_from_path，单个失败不中断其余加载。

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
        """
        从单个 .lua 文件加载插件

        流程：校验后缀 → 创建独立 LuaRuntimeManager 并初始化 → 用 LuaPluginWrapper
        包装 → load_from_file 执行脚本并读取元数据/注册 Hook → 注册到 PluginManager。
        任一步失败都会关闭该插件专属运行时，避免资源泄漏。

        Args:
            file_path: Lua 文件路径
            config: 插件配置

        Returns:
            bool: 是否加载成功
        """
        path = Path(file_path)

        if not path.exists():
            logger.error(f"Lua 插件文件不存在: {file_path}")
            return False

        if path.suffix != ".lua":
            logger.error(f"不支持的文件格式: {path.suffix}，期望 .lua")
            return False

        # 创建新的运行时实例（每个插件独立，共享客户端和配置）
        # 独立运行时保证插件间 Lua 全局环境互不污染，也便于单独释放
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
                    # 注册失败（如重名）时关闭插件并释放运行时
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
        """
        从 URL 加载 Lua 插件

        下载源码 → 写入临时 .lua 文件 → 复用 _load_from_file 加载，
        加载完成后无论成败都清理临时文件。

        Args:
            url: 插件源码 URL
            config: 插件配置

        Returns:
            bool: 是否加载成功
        """
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

        递归查找目录下所有 .lua 文件，跳过隐藏文件与 test_ 前缀的测试文件。
        返回待加载路径列表，实际加载由 load_from_path 完成。

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

        从 PluginManager 注销 → 关闭插件（释放其 Lua 运行时）→ 移除本地记录。

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
            List[Dict[str, Any]]: 每个元素为插件的元数据摘要（name/version/description/author/enabled）
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
