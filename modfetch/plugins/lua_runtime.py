"""
Lua 运行时集成

提供 Lua 脚本执行环境和与 Python 的桥接功能。
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import aiohttp
import lupa
from lupa import LuaRuntime

from modfetch.plugins.base import HookContext, HookResult, HookType, ModFetchPlugin
from modfetch.services import ModrinthClient
from modfetch.models import ModFetchConfig

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("modfetch")


class LuaPluginError(Exception):
    """Lua 插件错误"""

    pass


class LuaRuntimeManager:
    """
    Lua 运行时管理器

    管理 Lua 运行时实例，提供安全的脚本执行环境。
    """

    def __init__(
        self,
        modrinth_client: Optional[ModrinthClient] = None,
        config: Optional[ModFetchConfig] = None,
    ):
        self._runtime: Optional[LuaRuntime] = None
        self._globals: Dict[str, Any] = {}
        self._hooks: Dict[HookType, List[Callable]] = {}
        self._modrinth_client = modrinth_client
        self._config = config

    def initialize(self) -> None:
        """初始化 Lua 运行时"""
        # 创建 Lua 运行时
        self._runtime = LuaRuntime(unpack_returned_tuples=True)

        # 设置安全的全局环境
        self._setup_safe_globals()

        logger.debug("Lua 运行时已初始化")

    def _setup_safe_globals(self) -> None:
        """设置安全的 Lua 全局环境"""
        if not self._runtime:
            return

        # 基础数学库
        self._runtime.execute("""
            math = {
                abs = math.abs,
                ceil = math.ceil,
                floor = math.floor,
                max = math.max,
                min = math.min,
                random = math.random,
                randomseed = math.randomseed,
                huge = math.huge,
                pi = math.pi,
                sqrt = math.sqrt,
                pow = math.pow,
                exp = math.exp,
                log = math.log,
                log10 = math.log10,
                sin = math.sin,
                cos = math.cos,
                tan = math.tan,
                asin = math.asin,
                acos = math.acos,
                atan = math.atan,
                atan2 = math.atan2,
                deg = math.deg,
                rad = math.rad,
                mod = math.mod,
                fmod = math.fmod,
                frexp = math.frexp,
                ldexp = math.ldexp,
            }
        """)

        # 字符串库
        self._runtime.execute("""
            string = {
                byte = string.byte,
                char = string.char,
                find = string.find,
                format = string.format,
                gmatch = string.gmatch,
                gsub = string.gsub,
                len = string.len,
                lower = string.lower,
                match = string.match,
                rep = string.rep,
                reverse = string.reverse,
                sub = string.sub,
                upper = string.upper,
            }
        """)

        # 表库
        self._runtime.execute("""
            table = {
                concat = table.concat,
                insert = table.insert,
                maxn = table.maxn,
                remove = table.remove,
                sort = table.sort,
                unpack = table.unpack,
            }
        """)

        # 注册 Python 回调函数
        self._register_python_callbacks()

    def _register_python_callbacks(self) -> None:
        """注册 Python 回调函数到 Lua 环境"""
        if not self._runtime:
            return

        # 日志函数
        def lua_log(level: str, message: str) -> None:
            level = level.lower()
            if level == "debug":
                logger.debug(message)
            elif level == "info":
                logger.info(message)
            elif level == "warning" or level == "warn":
                logger.warning(message)
            elif level == "error":
                logger.error(message)
            else:
                logger.info(message)

        # JSON 处理
        def lua_json_encode(data: Any) -> str:
            try:
                return json.dumps(data)
            except Exception as e:
                raise LuaPluginError(f"JSON 编码失败: {e}")

        def lua_json_decode(text: str) -> Any:
            try:
                return json.loads(text)
            except Exception as e:
                raise LuaPluginError(f"JSON 解码失败: {e}")

        # 字符串处理
        def lua_split(text: str, delimiter: str) -> List[str]:
            return text.split(delimiter)

        def lua_trim(text: str) -> str:
            return text.strip()

        def lua_starts_with(text: str, prefix: str) -> bool:
            return text.startswith(prefix)

        def lua_ends_with(text: str, suffix: str) -> bool:
            return text.endswith(suffix)

        def lua_contains(text: str, substring: str) -> bool:
            return substring in text

        def lua_replace(text: str, old: str, new: str) -> str:
            return text.replace(old, new)

        def lua_lower(text: str) -> str:
            return text.lower()

        def lua_upper(text: str) -> str:
            return text.upper()

        def lua_sub(text: str, start: int, end: Optional[int] = None) -> str:
            if end is None:
                return text[start:]
            return text[start:end]

        def lua_match(text: str, pattern: str) -> Optional[str]:
            match = re.search(pattern, text)
            return match.group(0) if match else None

        def lua_match_all(text: str, pattern: str) -> List[str]:
            return re.findall(pattern, text)

        # 文件系统 API
        def lua_file_exists(path: str) -> bool:
            return Path(path).exists()

        def lua_file_read(path: str) -> str:
            try:
                return Path(path).read_text(encoding="utf-8")
            except Exception as e:
                raise LuaPluginError(f"读取文件失败: {e}")

        def lua_file_write(path: str, content: str) -> bool:
            try:
                Path(path).write_text(content, encoding="utf-8")
                return True
            except Exception as e:
                raise LuaPluginError(f"写入文件失败: {e}")

        def lua_file_append(path: str, content: str) -> bool:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
                return True
            except Exception as e:
                raise LuaPluginError(f"追加文件失败: {e}")

        def lua_file_delete(path: str) -> bool:
            try:
                Path(path).unlink()
                return True
            except Exception as e:
                raise LuaPluginError(f"删除文件失败: {e}")

        def lua_dir_exists(path: str) -> bool:
            return Path(path).is_dir()

        def lua_dir_create(path: str) -> bool:
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
                return True
            except Exception as e:
                raise LuaPluginError(f"创建目录失败: {e}")

        def lua_dir_list(path: str) -> List[str]:
            try:
                return [str(p) for p in Path(path).iterdir()]
            except Exception as e:
                raise LuaPluginError(f"列出目录失败: {e}")

        def lua_path_join(base: str, *parts: str) -> str:
            return str(Path(base).joinpath(*parts))

        def lua_path_dirname(path: str) -> str:
            return str(Path(path).parent)

        def lua_path_basename(path: str) -> str:
            return Path(path).name

        def lua_path_ext(path: str) -> str:
            return Path(path).suffix

        # HTTP 请求 API
        async def lua_http_get(
            url: str, headers: Optional[Dict[str, str]] = None
        ) -> Dict[str, Any]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers or {}) as response:
                        text = await response.text()
                        return {
                            "status": response.status,
                            "text": text,
                            "headers": dict(response.headers),
                            "success": 200 <= response.status < 300,
                        }
            except Exception as e:
                return {"success": False, "error": str(e)}

        async def lua_http_post(
            url: str, data: Union[str, Dict], headers: Optional[Dict[str, str]] = None
        ) -> Dict[str, Any]:
            try:
                async with aiohttp.ClientSession() as session:
                    if isinstance(data, dict):
                        async with session.post(
                            url, json=data, headers=headers or {}
                        ) as response:
                            text = await response.text()
                            return {
                                "status": response.status,
                                "text": text,
                                "headers": dict(response.headers),
                                "success": 200 <= response.status < 300,
                            }
                    else:
                        async with session.post(
                            url, data=data, headers=headers or {}
                        ) as response:
                            text = await response.text()
                            return {
                                "status": response.status,
                                "text": text,
                                "headers": dict(response.headers),
                                "success": 200 <= response.status < 300,
                            }
            except Exception as e:
                return {"success": False, "error": str(e)}

        def lua_url_encode(text: str) -> str:
            from urllib.parse import quote

            return quote(text)

        def lua_url_decode(text: str) -> str:
            from urllib.parse import unquote

            return unquote(text)

        def lua_url_join(base: str, url: str) -> str:
            return urljoin(base, url)

        def lua_url_parse(url: str) -> Dict[str, str]:
            parsed = urlparse(url)
            return {
                "scheme": parsed.scheme,
                "netloc": parsed.netloc,
                "path": parsed.path,
                "params": parsed.params,
                "query": parsed.query,
                "fragment": parsed.fragment,
            }

        # 工具函数 API
        def lua_time_now() -> float:
            return time.time()

        def lua_time_format(
            timestamp: Optional[float] = None, fmt: str = "%Y-%m-%d %H:%M:%S"
        ) -> str:
            if timestamp is None:
                timestamp = time.time()
            return datetime.fromtimestamp(timestamp).strftime(fmt)

        def lua_sleep(seconds: float) -> None:
            time.sleep(seconds)

        def lua_hash_md5(text: str) -> str:
            return hashlib.md5(text.encode()).hexdigest()

        def lua_hash_sha1(text: str) -> str:
            return hashlib.sha1(text.encode()).hexdigest()

        def lua_hash_sha256(text: str) -> str:
            return hashlib.sha256(text.encode()).hexdigest()

        def lua_base64_encode(text: str) -> str:
            import base64

            return base64.b64encode(text.encode()).decode()

        def lua_base64_decode(text: str) -> str:
            import base64

            return base64.b64decode(text.encode()).decode()

        def lua_random_int(min_val: int, max_val: int) -> int:
            import random

            return random.randint(min_val, max_val)

        def lua_random_float() -> float:
            import random

            return random.random()

        def lua_random_choice(items: List[Any]) -> Any:
            import random

            return random.choice(items)

        def lua_uuid() -> str:
            import uuid

            return str(uuid.uuid4())

        # 注册到 Lua 全局
        self._runtime.globals()["modfetch"] = {
            # 日志
            "log": lua_log,
            # JSON
            "json_encode": lua_json_encode,
            "json_decode": lua_json_decode,
            # 字符串
            "split": lua_split,
            "trim": lua_trim,
            "starts_with": lua_starts_with,
            "ends_with": lua_ends_with,
            "contains": lua_contains,
            "replace": lua_replace,
            "lower": lua_lower,
            "upper": lua_upper,
            "sub": lua_sub,
            "match": lua_match,
            "match_all": lua_match_all,
            # 文件系统
            "file_exists": lua_file_exists,
            "file_read": lua_file_read,
            "file_write": lua_file_write,
            "file_append": lua_file_append,
            "file_delete": lua_file_delete,
            "dir_exists": lua_dir_exists,
            "dir_create": lua_dir_create,
            "dir_list": lua_dir_list,
            "path_join": lua_path_join,
            "path_dirname": lua_path_dirname,
            "path_basename": lua_path_basename,
            "path_ext": lua_path_ext,
            # HTTP
            "http_get": lua_http_get,
            "http_post": lua_http_post,
            "url_encode": lua_url_encode,
            "url_decode": lua_url_decode,
            "url_join": lua_url_join,
            "url_parse": lua_url_parse,
            # 工具函数
            "time_now": lua_time_now,
            "time_format": lua_time_format,
            "sleep": lua_sleep,
            "hash_md5": lua_hash_md5,
            "hash_sha1": lua_hash_sha1,
            "hash_sha256": lua_hash_sha256,
            "base64_encode": lua_base64_encode,
            "base64_decode": lua_base64_decode,
            "random_int": lua_random_int,
            "random_float": lua_random_float,
            "random_choice": lua_random_choice,
            "uuid": lua_uuid,
        }

        # 如果有 ModrinthClient，注册 Modrinth API
        if self._modrinth_client:
            self._register_modrinth_api()

    def _register_modrinth_api(self) -> None:
        """注册 Modrinth API 到 Lua 环境"""
        if not self._runtime or not self._modrinth_client:
            return

        client = self._modrinth_client

        # 获取项目信息
        async def lua_modrinth_get_project(project_id: str) -> Dict[str, Any]:
            try:
                project = await client.get_project(project_id)
                if project:
                    return {
                        "success": True,
                        "id": project.id,
                        "name": project.name,
                        "title": project.title,
                        "description": project.description,
                        "project_type": project.project_type,
                        "versions": project.versions,
                    }
                return {"success": False, "error": "项目未找到"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # 获取版本信息
        async def lua_modrinth_get_version(
            project_id: str,
            mc_version: str,
            mod_loader: str,
            specific_version: Optional[str] = None,
        ) -> Dict[str, Any]:
            try:
                version_info, file_info = await client.get_version(
                    project_id, mc_version, mod_loader, specific_version
                )
                if version_info:
                    result = {
                        "success": True,
                        "version": {
                            "id": version_info.id,
                            "name": version_info.name,
                            "version": version_info.version,
                            "loaders": [str(l) for l in version_info.loaders],
                            "game_versions": version_info.game_versions,
                        },
                    }
                    if version_info.dependencies:
                        result["version"]["dependencies"] = [
                            {
                                "project_id": dep.project_id,
                                "dependency_type": dep.dependency_type,
                            }
                            for dep in version_info.dependencies
                        ]
                    if file_info:
                        result["file"] = {
                            "url": file_info.get("url"),
                            "filename": file_info.get("filename"),
                            "size": file_info.get("size"),
                            "sha1": file_info.get("hashes", {}).get("sha1"),
                        }
                    return result
                return {"success": False, "error": "版本未找到"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # 搜索项目
        async def lua_modrinth_search(
            query: str, facets: Optional[List[str]] = None, limit: int = 10
        ) -> Dict[str, Any]:
            try:
                params = {"query": query, "limit": limit}
                if facets:
                    params["facets"] = facets

                async with client.session.get(
                    f"{client.__class__.__module__}.MODRINTH_BASE_URL/search",
                    params=params,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "hits": data.get("hits", []),
                            "total": data.get("total_hits", 0),
                        }
                    return {"success": False, "error": f"HTTP {response.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # 获取加载器版本
        async def lua_modrinth_get_loader_version(
            mc_version: str, loader: str
        ) -> Dict[str, Any]:
            try:
                if loader == "fabric":
                    version = await client.get_fabric_version(mc_version)
                elif loader == "quilt":
                    version = await client.get_quilt_version(mc_version)
                elif loader == "forge":
                    version = await client.get_forge_version(mc_version)
                else:
                    return {"success": False, "error": "不支持的加载器"}

                if version:
                    return {"success": True, "version": version}
                return {"success": False, "error": "未找到版本"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # 注册到 modrinth 命名空间
        modfetch_table = self._runtime.globals()["modfetch"]
        modfetch_table["modrinth"] = {
            "get_project": lua_modrinth_get_project,
            "get_version": lua_modrinth_get_version,
            "search": lua_modrinth_search,
            "get_loader_version": lua_modrinth_get_loader_version,
        }

        # 如果有配置，注册配置 API
        if self._config:
            self._register_config_api()

    def _register_config_api(self) -> None:
        """注册配置 API 到 Lua 环境"""
        if not self._runtime or not self._config:
            return

        config = self._config

        # 获取完整配置
        def lua_config_get() -> Dict[str, Any]:
            return {
                "minecraft": {
                    "version": config.minecraft.version,
                    "mod_loader": str(config.minecraft.mod_loader),
                    "mods_count": len(config.minecraft.mods),
                },
                "output": {
                    "download_dir": config.output.download_dir,
                    "format": [f.value for f in config.output.format],
                }
                if config.output
                else {},
            }

        # 获取 Minecraft 配置
        def lua_config_get_minecraft() -> Dict[str, Any]:
            mods_list = []
            for mod in config.minecraft.mods:
                if isinstance(mod, str):
                    mods_list.append({"id": mod, "slug": None})
                else:
                    mods_list.append({"id": mod.id, "slug": mod.slug})

            return {
                "version": config.minecraft.version,
                "mod_loader": str(config.minecraft.mod_loader),
                "mods": mods_list,
            }

        # 获取输出配置
        def lua_config_get_output() -> Dict[str, Any]:
            if not config.output:
                return {}
            return {
                "download_dir": config.output.download_dir,
                "format": [f.value for f in config.output.format],
            }

        # 获取插件配置
        def lua_config_get_plugin(plugin_name: str) -> Dict[str, Any]:
            if config.plugins and hasattr(config.plugins, "configs"):
                return config.plugins.configs.get(plugin_name, {})
            return {}

        # 获取所有模组列表
        def lua_config_get_mods() -> List[Dict[str, Any]]:
            mods_list = []
            for mod in config.minecraft.mods:
                if isinstance(mod, str):
                    mods_list.append({"id": mod, "slug": None})
                else:
                    mods_list.append({"id": mod.id, "slug": mod.slug})
            return mods_list

        # 注册到 config 命名空间
        modfetch_table = self._runtime.globals()["modfetch"]
        modfetch_table["config"] = {
            "get": lua_config_get,
            "get_minecraft": lua_config_get_minecraft,
            "get_output": lua_config_get_output,
            "get_plugin": lua_config_get_plugin,
            "get_mods": lua_config_get_mods,
        }

    def execute_script(self, script: str, filename: str = "<string>") -> Any:
        """
        执行 Lua 脚本

        Args:
            script: Lua 脚本代码
            filename: 脚本文件名（用于错误信息）

        Returns:
            脚本执行结果
        """
        if not self._runtime:
            raise LuaPluginError("Lua 运行时未初始化")

        try:
            return self._runtime.execute(script)
        except lupa.LuaError as e:
            raise LuaPluginError(f"Lua 执行错误 [{filename}]: {e}")

    def execute_file(self, file_path: Union[str, Path]) -> Any:
        """
        执行 Lua 文件

        Args:
            file_path: Lua 文件路径

        Returns:
            脚本执行结果
        """
        path = Path(file_path)
        if not path.exists():
            raise LuaPluginError(f"Lua 文件不存在: {file_path}")

        script = path.read_text(encoding="utf-8")
        return self.execute_script(script, str(path))

    def call_function(self, func_name: str, *args) -> Any:
        """
        调用 Lua 函数

        Args:
            func_name: 函数名
            *args: 函数参数

        Returns:
            函数返回值
        """
        if not self._runtime:
            raise LuaPluginError("Lua 运行时未初始化")

        try:
            func = self._runtime.globals()[func_name]
            if callable(func):
                return func(*args)
            else:
                raise LuaPluginError(f"'{func_name}' 不是可调用的函数")
        except lupa.LuaError as e:
            raise LuaPluginError(f"调用函数 {func_name} 失败: {e}")

    def get_global(self, name: str) -> Any:
        """获取 Lua 全局变量"""
        if not self._runtime:
            return None
        try:
            return self._runtime.globals()[name]
        except KeyError:
            return None

    def set_global(self, name: str, value: Any) -> None:
        """设置 Lua 全局变量"""
        if not self._runtime:
            raise LuaPluginError("Lua 运行时未初始化")
        self._runtime.globals()[name] = value

    def shutdown(self) -> None:
        """关闭 Lua 运行时"""
        self._runtime = None
        self._hooks.clear()
        logger.debug("Lua 运行时已关闭")


class LuaPluginWrapper(ModFetchPlugin):
    """
    Lua 插件包装器

    将 Lua 脚本包装为符合 ModFetchPlugin 接口的插件。
    """

    # 类属性 - 在 __init__ 中会被覆盖
    name: str = ""
    _version: str = "1.0.0"
    _description: str = ""
    _author: str = ""
    dependencies: List[str] = []

    def __init__(self, name: str, runtime: LuaRuntimeManager):
        self.name = name
        self._runtime = runtime
        self._metadata: Dict[str, Any] = {
            "version": "1.0.0",
            "description": "",
            "author": "",
        }
        self._hooks: Dict[HookType, str] = {}  # HookType -> Lua 函数名
        self._enabled = True

    @property
    def version(self) -> str:  # type: ignore
        return self._metadata.get("version", "1.0.0")

    @property
    def description(self) -> str:  # type: ignore
        return self._metadata.get("description", "")

    @property
    def author(self) -> str:  # type: ignore
        return self._metadata.get("author", "")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def load_from_file(self, file_path: Union[str, Path]) -> bool:
        """
        从文件加载 Lua 插件

        Args:
            file_path: Lua 文件路径

        Returns:
            是否加载成功
        """
        try:
            self._runtime.execute_file(file_path)

            # 读取插件元数据
            plugin_table = self._runtime.get_global("plugin")
            if plugin_table:
                # Lua 表没有 .get() 方法，需要手动处理
                try:
                    version = plugin_table["version"]
                except (KeyError, TypeError):
                    version = "1.0.0"
                try:
                    description = plugin_table["description"]
                except (KeyError, TypeError):
                    description = ""
                try:
                    author = plugin_table["author"]
                except (KeyError, TypeError):
                    author = ""

                self._metadata = {
                    "version": version,
                    "description": description,
                    "author": author,
                }

            # 注册 Hook
            self._register_hooks()

            logger.info(f"Lua 插件 {self.name} 加载成功")
            return True

        except Exception as e:
            logger.error(f"加载 Lua 插件 {self.name} 失败: {e}")
            return False

    def _register_hooks(self) -> None:
        """从 Lua 脚本注册 Hook"""
        hook_mapping = {
            "on_config_loaded": HookType.CONFIG_LOADED,
            "on_config_validated": HookType.CONFIG_VALIDATED,
            "on_pre_resolve": HookType.PRE_RESOLVE,
            "on_post_resolve": HookType.POST_RESOLVE,
            "on_pre_resolve_dependencies": HookType.PRE_RESOLVE_DEPENDENCIES,
            "on_post_resolve_dependencies": HookType.POST_RESOLVE_DEPENDENCIES,
            "on_pre_download": HookType.PRE_DOWNLOAD,
            "on_download_progress": HookType.DOWNLOAD_PROGRESS,
            "on_post_download": HookType.POST_DOWNLOAD,
            "on_download_failed": HookType.DOWNLOAD_FAILED,
            "on_pre_package": HookType.PRE_PACKAGE,
            "on_post_package": HookType.POST_PACKAGE,
            "on_plugin_load": HookType.PLUGIN_LOAD,
            "on_plugin_unload": HookType.PLUGIN_UNLOAD,
        }

        for func_name, hook_type in hook_mapping.items():
            func = self._runtime.get_global(func_name)
            if callable(func):
                self._hooks[hook_type] = func_name

    def register_hooks(self) -> Dict[HookType, Callable]:
        """
        注册 Hook 处理器

        Returns:
            Hook 类型到处理函数的映射
        """
        handlers: Dict[HookType, Callable] = {}

        for hook_type, func_name in self._hooks.items():
            handlers[hook_type] = self._create_handler(func_name)

        return handlers

    def _create_handler(self, func_name: str) -> Callable:
        """创建 Python 包装的处理函数"""

        def handler(context: HookContext) -> HookResult:
            try:
                # 转换上下文为 Lua 表
                lua_context = self._context_to_lua(context)

                # 调用 Lua 函数
                func = self._runtime.get_global(func_name)
                if func and callable(func):
                    result = func(lua_context)

                    # 转换结果
                    if result is None:
                        return HookResult()
                    elif isinstance(result, dict):
                        return HookResult(
                            success=result.get("success", True),
                            data=result.get("data"),
                            error=result.get("error"),
                            should_stop=result.get("should_stop", False),
                        )
                    else:
                        return HookResult(data=result)

                return HookResult()

            except Exception as e:
                logger.error(f"Lua Hook {func_name} 执行失败: {e}")
                return HookResult(success=False, error=str(e))

        return handler

    def _context_to_lua(self, context: HookContext) -> Dict[str, Any]:
        """将 HookContext 转换为 Lua 表"""
        return {
            "config": self._config_to_lua(context.config),
            "version": context.version,
            "mod_entry": self._mod_entry_to_lua(context.mod_entry)
            if context.mod_entry
            else None,
            "download_info": context.download_info,
            "extra_data": context.extra_data,
        }

    def _config_to_lua(self, config) -> Dict[str, Any]:
        """将配置转换为 Lua 表"""
        # 简化的配置转换
        return {
            "minecraft_version": getattr(config, "minecraft_version", None),
            "mod_loader": getattr(config, "mod_loader", None),
            "mods_count": len(getattr(config, "mods", [])),
        }

    def _mod_entry_to_lua(self, mod_entry) -> Dict[str, Any]:
        """将 ModEntry 转换为 Lua 表"""
        return {
            "id": getattr(mod_entry, "id", None),
            "name": getattr(mod_entry, "name", None),
            "version": getattr(mod_entry, "version", None),
        }

    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化插件"""
        # 将配置传递给 Lua
        if self._runtime._runtime:
            self._runtime._runtime.globals()["plugin_config"] = config

        logger.debug(f"Lua 插件 {self.name} 已初始化")

    async def shutdown(self) -> None:
        """关闭插件"""
        logger.debug(f"Lua 插件 {self.name} 已关闭")
