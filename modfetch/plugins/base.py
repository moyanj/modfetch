"""
插件系统基类

定义插件接口、Hook类型和生命周期管理。
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("modfetch")

from modfetch.domain.config_models import ModEntry, ModFetchConfig


class HookType(Enum):
    """
    Hook 类型定义

    枚举构建流程中所有可被插件拦截/观察的阶段点，按生命周期分组：
    配置 → 解析 → 下载 → 打包 → 插件自身生命周期。
    插件通过 register_hooks() 返回 {HookType: handler} 映射来订阅这些阶段，
    执行引擎在对应阶段触发时按注册顺序调用 handler。
    """

    # 配置阶段
    CONFIG_LOADED = auto()  # 配置加载完成后
    CONFIG_VALIDATED = auto()  # 配置验证完成后

    # 解析阶段
    PRE_RESOLVE = auto()  # 开始解析模组前
    POST_RESOLVE = auto()  # 解析模组完成后
    PRE_RESOLVE_DEPENDENCIES = auto()  # 开始解析依赖前
    POST_RESOLVE_DEPENDENCIES = auto()  # 解析依赖完成后

    # 下载阶段
    PRE_DOWNLOAD = auto()  # 开始下载前
    DOWNLOAD_PROGRESS = auto()  # 下载进度更新
    POST_DOWNLOAD = auto()  # 下载完成后
    DOWNLOAD_FAILED = auto()  # 下载失败时

    # 打包阶段
    PRE_PACKAGE = auto()  # 开始打包前
    POST_PACKAGE = auto()  # 打包完成后

    # 生命周期
    PLUGIN_LOAD = auto()  # 插件加载时
    PLUGIN_UNLOAD = auto()  # 插件卸载时


@dataclass
class HookContext:
    """
    Hook 上下文信息

    触发 Hook 时由执行引擎构造并传入，承载当前构建阶段的相关数据。
    不同 Hook 阶段会填充不同字段，插件应只读取与自身订阅阶段相关的字段，
    其余字段可能为 None。
    """

    config: ModFetchConfig  # 当前构建的完整配置
    version: Optional[str] = None  # 当前处理的 Minecraft 版本（多版本构建时区分）
    mod_entry: Optional[ModEntry] = None  # 当前处理的模组条目（解析/下载阶段）
    download_info: Optional[Dict[str, Any]] = None  # 下载结果信息（下载阶段）
    # 扩展数据字典，供插件间/插件与引擎间传递自定义信息
    extra_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """
    Hook 执行结果

    插件处理函数返回此对象，向执行引擎反馈处理结果。
    默认全部成功；仅当需要中断流程或上报失败时才修改字段。
    """

    success: bool = True  # 是否执行成功；False 表示该阶段处理失败
    data: Any = None  # 附加数据，可携带任意自定义结果供后续使用
    error: Optional[str] = None  # 失败时的错误信息
    should_stop: bool = False  # 是否阻止后续处理（中断当前 Hook 链及后续阶段）


class ModFetchPlugin(ABC):
    """
    ModFetch 插件基类

    所有插件必须继承此类并实现必要的方法。
    子类需声明 name/version/description/author 元数据，并实现 register_hooks()
    返回 {HookType: handler} 映射；handler 接收 HookContext 并返回 HookResult。
    """

    # 插件元数据（子类应覆盖这些类属性）
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = []  # 依赖的其他插件名列表

    def __init__(self):
        self._enabled = True  # 插件启用状态
        self._config: Dict[str, Any] = {}  # 插件配置（initialize 时注入）

    @property
    def enabled(self) -> bool:
        """插件是否启用"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        """设置插件启用状态"""
        self._enabled = value

    @property
    def config(self) -> Dict[str, Any]:
        """插件配置"""
        return self._config

    @abstractmethod
    def register_hooks(self) -> Dict[HookType, Callable]:
        """
        注册 Hook 处理器

        Returns:
            Dict[HookType, Callable]: Hook 类型到处理函数的映射
        """
        pass

    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        插件初始化

        Args:
            config: 插件配置字典
        """
        self._config = config
        logger.debug(f"插件 {self.name} 已初始化")

    async def shutdown(self) -> None:
        """插件关闭清理"""
        logger.debug(f"插件 {self.name} 已关闭")

    def on_config_loaded(self, context: HookContext) -> HookResult:
        """
        配置加载完成 Hook

        可以在此修改或验证配置。
        """
        return HookResult()

    def on_config_validated(self, context: HookContext) -> HookResult:
        """配置验证完成 Hook（可在此对已验证的配置做二次校验或补充）"""
        return HookResult()

    def on_pre_resolve(self, context: HookContext) -> HookResult:
        """解析模组前 Hook（context.mod_entry 为待解析模组，可在此过滤/改写）"""
        return HookResult()

    def on_post_resolve(self, context: HookContext) -> HookResult:
        """解析模组后 Hook（模组信息已解析完成）"""
        return HookResult()

    def on_pre_resolve_dependencies(self, context: HookContext) -> HookResult:
        """解析依赖前 Hook（可在此干预依赖解析流程）"""
        return HookResult()

    def on_post_resolve_dependencies(self, context: HookContext) -> HookResult:
        """解析依赖后 Hook（依赖图已构建完成）"""
        return HookResult()

    def on_pre_download(self, context: HookContext) -> HookResult:
        """下载前 Hook（可在此做下载前的准备或拦截）"""
        return HookResult()

    def on_download_progress(self, context: HookContext) -> HookResult:
        """下载进度 Hook（context.download_info 携带进度信息）"""
        return HookResult()

    def on_post_download(self, context: HookContext) -> HookResult:
        """下载完成 Hook（context.download_info 携带下载结果）"""
        return HookResult()

    def on_download_failed(self, context: HookContext) -> HookResult:
        """下载失败 Hook（context.download_info 携带失败信息）"""
        return HookResult()

    def on_pre_package(self, context: HookContext) -> HookResult:
        """打包前 Hook（可在此做打包准备或拦截）"""
        return HookResult()

    def on_post_package(self, context: HookContext) -> HookResult:
        """打包完成 Hook（context.extra_data 通常携带输出路径/格式）"""
        return HookResult()

    def on_plugin_load(self, context: HookContext) -> HookResult:
        """插件加载 Hook（插件被加载进管理器时触发）"""
        return HookResult()

    def on_plugin_unload(self, context: HookContext) -> HookResult:
        """插件卸载 Hook（插件被移除时触发，可做清理）"""
        return HookResult()


class PluginManager:
    """
    插件管理器

    负责插件的加载、注册和 Hook 调用。
    """

    def __init__(self):
        """
        初始化插件管理器

        - _plugins: 已注册插件，key 为插件名
        - _hooks: 每种 HookType 对应的 handler 列表（按注册顺序追加）
        - _hook_order: 每种 HookType 对应的插件名列表，与 _hooks 一一对应，
          用于追溯 handler 来源，卸载时据此精确移除
        """
        self._plugins: Dict[str, ModFetchPlugin] = {}
        self._hooks: Dict[HookType, List[Callable]] = {hook: [] for hook in HookType}
        self._hook_order: Dict[HookType, List[str]] = {hook: [] for hook in HookType}

    def register_plugin(
        self, plugin: ModFetchPlugin, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        注册插件

        将插件实例登记进管理器：先初始化（若有配置则异步调用），
        再收集 register_hooks() 返回的 handler 挂载到对应 HookType 队列。

        Args:
            plugin: 插件实例
            config: 插件配置

        Returns:
            bool: 是否注册成功
        """
        if plugin.name in self._plugins:
            logger.warning(f"插件 {plugin.name} 已存在，跳过注册")
            return False

        try:
            # 初始化插件
            if config:
                import asyncio

                asyncio.create_task(plugin.initialize(config))

            # 注册插件
            self._plugins[plugin.name] = plugin

            # 注册 Hook
            hooks = plugin.register_hooks()
            for hook_type, handler in hooks.items():
                if hook_type in self._hooks:
                    self._hooks[hook_type].append(handler)
                    self._hook_order[hook_type].append(plugin.name)

            logger.info(f"插件 {plugin.name} v{plugin.version} 注册成功")
            return True

        except Exception as e:
            logger.error(f"插件 {plugin.name} 注册失败: {e}")
            return False

    def unregister_plugin(self, plugin_name: str) -> bool:
        """
        卸载插件

        与 register_plugin 对称：先从各 HookType 队列中移除该插件的 handler，
        再异步调用 shutdown() 清理资源，最后从 _plugins 中移除。

        Args:
            plugin_name: 插件名称

        Returns:
            bool: 是否卸载成功
        """
        if plugin_name not in self._plugins:
            logger.warning(f"插件 {plugin_name} 不存在")
            return False

        plugin = self._plugins[plugin_name]

        try:
            # 清理 Hook
            hooks = plugin.register_hooks()
            for hook_type, handler in hooks.items():
                if hook_type in self._hooks and handler in self._hooks[hook_type]:
                    self._hooks[hook_type].remove(handler)
                    self._hook_order[hook_type].remove(plugin_name)

            # 关闭插件
            import asyncio

            asyncio.create_task(plugin.shutdown())

            # 移除插件
            del self._plugins[plugin_name]

            logger.info(f"插件 {plugin_name} 已卸载")
            return True

        except Exception as e:
            logger.error(f"插件 {plugin_name} 卸载失败: {e}")
            return False

    async def execute_hook(
        self, hook_type: HookType, context: HookContext
    ) -> List[HookResult]:
        """
        执行指定类型的所有 Hook

        按注册顺序依次调用该 HookType 的 handler；handler 可为同步或异步函数，
        返回值会被规范化为 HookResult。若某个 handler 返回 should_stop=True，
        则中断后续 handler 的执行。

        Args:
            hook_type: Hook 类型
            context: Hook 上下文

        Returns:
            List[HookResult]: 所有 Hook 的执行结果
        """
        results = []
        handlers = self._hooks.get(hook_type, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(context)
                else:
                    result = handler(context)

                if result is None:
                    result = HookResult()
                elif not isinstance(result, HookResult):
                    result = HookResult(data=result)

                results.append(result)

                # 如果有 Hook 要求停止，则中断
                if result.should_stop:
                    logger.debug(f"Hook {hook_type.name} 被阻止")
                    break

            except Exception as e:
                logger.error(f"Hook {hook_type.name} 执行失败: {e}")
                results.append(HookResult(success=False, error=str(e)))

        return results

    def get_plugin(self, name: str) -> Optional[ModFetchPlugin]:
        """获取指定名称的插件实例，未注册时返回 None"""
        return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有已注册的插件

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
            for p in self._plugins.values()
        ]

    def enable_plugin(self, name: str) -> bool:
        """
        启用插件

        Args:
            name: 插件名称

        Returns:
            bool: 插件是否存在并已启用
        """
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = True
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        """
        禁用插件

        Args:
            name: 插件名称

        Returns:
            bool: 插件是否存在并已禁用
        """
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = False
            return True
        return False


import asyncio
