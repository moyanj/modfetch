"""
插件加载器

支持从本地文件、Python 模块或远程 URL 加载插件。
"""

import ast
import importlib
import importlib.util
import inspect
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from urllib.parse import urlparse

import aiohttp

from modfetch.plugins.base import ModFetchPlugin, PluginManager
from modfetch.exceptions import ModFetchError

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("modfetch")


class PluginLoadError(ModFetchError):
    """插件加载错误"""

    pass


class PluginLoader:
    """
    插件加载器

    支持多种方式加载插件：
    1. 本地 Python 文件 (.py)
    2. 本地插件目录
    3. Python 模块路径 (modfetch.plugins.xxx)
    4. 远程 URL (HTTP/HTTPS)
    """

    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._loaded_modules: Dict[str, Any] = {}

    async def load_from_path(
        self, path: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从路径加载插件

        Args:
            path: 插件路径（文件、目录或模块名）
            config: 插件配置

        Returns:
            bool: 是否加载成功
        """
        # 判断路径类型
        if path.startswith("http://") or path.startswith("https://"):
            return await self._load_from_url(path, config)
        elif os.path.isfile(path):
            return await self._load_from_file(path, config)
        elif os.path.isdir(path):
            return await self._load_from_directory(path, config)
        else:
            # 尝试作为模块名加载
            return await self.load_from_module(path, config)

    async def load_multiple(
        self, paths: List[str], configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, bool]:
        """
        批量加载插件

        Args:
            paths: 插件路径列表
            configs: 插件配置字典，key 为路径

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
                logger.error(f"加载插件 {path} 失败: {e}")
                results[path] = False

        return results

    async def _load_from_file(
        self, file_path: str, config: Optional[Dict[str, Any]]
    ) -> bool:
        """从 Python 文件加载插件"""
        path = Path(file_path)

        if not path.exists():
            raise PluginLoadError(f"插件文件不存在: {file_path}")

        if path.suffix != ".py":
            raise PluginLoadError(f"不支持的文件格式: {path.suffix}")

        # 读取并验证文件
        source = path.read_text(encoding="utf-8")
        self._validate_plugin_source(source)

        # 动态加载模块
        module_name = f"modfetch_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"无法创建模块规范: {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        return self._register_plugin_from_module(module, config)

    async def _load_from_directory(
        self, dir_path: str, config: Optional[Dict[str, Any]]
    ) -> bool:
        """从目录加载插件"""
        path = Path(dir_path)

        if not path.exists():
            raise PluginLoadError(f"插件目录不存在: {dir_path}")

        # 查找目录中的 __init__.py 或主插件文件
        init_file = path / "__init__.py"
        if init_file.exists():
            return await self._load_from_file(str(init_file), config)

        # 查找其他 .py 文件
        py_files = list(path.glob("*.py"))
        if not py_files:
            raise PluginLoadError(f"目录中没有找到 Python 文件: {dir_path}")

        # 加载第一个找到的插件文件
        return await self._load_from_file(str(py_files[0]), config)

    async def load_from_module(
        self, module_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从 Python 模块加载插件（公共方法）

        Args:
            module_name: 模块名称（如 'modfetch.plugins.builtin.myplugin'）
            config: 插件配置

        Returns:
            bool: 是否加载成功
        """
        try:
            # 尝试导入模块
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                module = importlib.import_module(module_name)

            return self._register_plugin_from_module(module, config)

        except ImportError as e:
            raise PluginLoadError(f"无法导入模块 {module_name}: {e}")

    async def _load_from_url(self, url: str, config: Optional[Dict[str, Any]]) -> bool:
        """从远程 URL 加载插件"""
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise PluginLoadError(f"不支持的 URL 协议: {parsed.scheme}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise PluginLoadError(f"无法下载插件: HTTP {response.status}")

                    source = await response.text()

        except aiohttp.ClientError as e:
            raise PluginLoadError(f"下载插件失败: {e}")

        # 验证源码
        self._validate_plugin_source(source)

        # 创建临时文件
        filename = Path(parsed.path).name or "plugin.py"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
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

    def _validate_plugin_source(self, source: str) -> bool:
        """
        验证插件源码安全性

        检查是否包含危险操作。
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            raise PluginLoadError(f"插件源码语法错误: {e}")

        # 检查危险导入
        dangerous_modules = {
            "os.system",
            "subprocess",
            "eval",
            "exec",
            "compile",
            "__import__",
            "importlib",
            "sys.modules",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in dangerous_modules:
                        logger.warning(f"插件包含潜在危险导入: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module in dangerous_modules:
                    logger.warning(f"插件包含潜在危险导入: {node.module}")

        return True

    def _register_plugin_from_module(
        self, module: Any, config: Optional[Dict[str, Any]]
    ) -> bool:
        """
        从模块中查找并注册插件类

        Args:
            module: Python 模块
            config: 插件配置

        Returns:
            bool: 是否成功注册
        """
        plugin_classes = []

        # 查找模块中所有的插件类
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, ModFetchPlugin)
                and obj is not ModFetchPlugin
                and hasattr(obj, "name")
                and obj.name
            ):
                plugin_classes.append(obj)

        if not plugin_classes:
            raise PluginLoadError("模块中没有找到有效的插件类")

        # 注册第一个找到的插件类
        plugin_class = plugin_classes[0]
        plugin = plugin_class()

        return self.plugin_manager.register_plugin(plugin, config)

    def scan_directory(self, directory: str) -> List[str]:
        """
        扫描目录中的所有插件

        Args:
            directory: 要扫描的目录

        Returns:
            List[str]: 插件路径列表
        """
        path = Path(directory)
        if not path.exists():
            return []

        plugin_paths = []

        # 查找所有 .py 文件
        for py_file in path.rglob("*.py"):
            # 跳过 __pycache__ 和测试文件
            if "__pycache__" in str(py_file) or py_file.name.startswith("test_"):
                continue
            plugin_paths.append(str(py_file))

        return plugin_paths
