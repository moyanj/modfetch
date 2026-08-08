"""插件系统基类（base.py）单元测试

覆盖 HookType / HookContext / HookResult / ModFetchPlugin / PluginManager
的默认行为、注册/卸载/执行 Hook 的完整生命周期。
"""

import asyncio

import pytest

from modfetch.domain.config_models import ModEntry, ModFetchConfig
from modfetch.plugins.base import (
    HookContext,
    HookResult,
    HookType,
    ModFetchPlugin,
    PluginManager,
)


def _make_config() -> ModFetchConfig:
    """构造最小合法配置，供 HookContext 使用"""
    return ModFetchConfig.from_dict(
        {"minecraft": {"version": ["1.21.1"], "mods": ["sodium"]}}
    )


class DummyPlugin(ModFetchPlugin):
    """最小可实例化插件：仅实现抽象方法 register_hooks"""

    name = "dummy"
    version = "1.0.0"
    description = "dummy plugin"
    author = "test"

    def register_hooks(self):
        return {HookType.CONFIG_LOADED: self.on_config_loaded}


class TestHookType:
    def test_members(self):
        """HookType 枚举成员完整且顺序稳定（auto 从 1 开始）"""
        assert len(HookType) == 14
        assert HookType.CONFIG_LOADED.value == 1
        assert HookType.PLUGIN_UNLOAD.value == 14


class TestHookContext:
    def test_defaults(self):
        """未显式传入的字段默认 None / 空字典"""
        ctx = HookContext(config=_make_config())
        assert ctx.version is None
        assert ctx.mod_entry is None
        assert ctx.download_info is None
        assert ctx.extra_data == {}

    def test_fields(self):
        """显式传入的字段原样保留"""
        config = _make_config()
        entry = ModEntry(id="sodium")
        ctx = HookContext(
            config=config,
            version="1.21.1",
            mod_entry=entry,
            download_info={"filename": "a.jar"},
        )
        assert ctx.config is config
        assert ctx.version == "1.21.1"
        assert ctx.mod_entry is entry
        assert ctx.download_info == {"filename": "a.jar"}


class TestHookResult:
    def test_defaults(self):
        """默认全部成功、无附加数据"""
        r = HookResult()
        assert r.success is True
        assert r.data is None
        assert r.error is None
        assert r.should_stop is False

    def test_custom(self):
        """自定义字段生效"""
        r = HookResult(success=False, data={"x": 1}, error="boom", should_stop=True)
        assert r.success is False
        assert r.data == {"x": 1}
        assert r.error == "boom"
        assert r.should_stop is True


class TestModFetchPlugin:
    def test_enabled_property(self):
        """enabled 属性可读写"""
        plugin = DummyPlugin()
        assert plugin.enabled is True
        plugin.enabled = False
        assert plugin.enabled is False

    def test_config_property_default(self):
        """config 属性默认空字典"""
        plugin = DummyPlugin()
        assert plugin.config == {}

    def test_abstract_register_hooks_base(self):
        """直接调用基类抽象方法（绕过 override）返回 None"""
        plugin = DummyPlugin()
        assert ModFetchPlugin.register_hooks(plugin) is None

    def test_default_hook_handlers_return_success(self):
        """所有默认 on_* 处理器返回成功 HookResult"""
        plugin = DummyPlugin()
        context = HookContext(config=_make_config())
        for hook in HookType:
            handler = getattr(plugin, f"on_{hook.name.lower()}")
            result = handler(context)
            assert isinstance(result, HookResult)
            assert result.success is True

    async def test_initialize_sets_config(self):
        """initialize 注入配置"""
        plugin = DummyPlugin()
        await plugin.initialize({"key": "value"})
        assert plugin.config == {"key": "value"}

    async def test_shutdown(self):
        """shutdown 不抛异常"""
        plugin = DummyPlugin()
        await plugin.shutdown()


class TestLoguruFallback:
    def test_fallback_to_stdlib_logging(self, monkeypatch):
        """loguru 不可导入时回退到标准库 logging"""
        import importlib
        import logging
        import sys

        import modfetch.plugins
        import modfetch.plugins.base as original_base

        # 置空 loguru 触发 ImportError，随后重新导入模块
        monkeypatch.setitem(sys.modules, "loguru", None)
        monkeypatch.delitem(sys.modules, "modfetch.plugins.base")
        mod = importlib.import_module("modfetch.plugins.base")
        assert isinstance(mod.logger, logging.Logger)
        assert mod.logger.name == "modfetch"
        # 手动恢复：re-import 会同时改写 sys.modules 与包属性
        # modfetch.plugins.base，monkeypatch 只还原前者，需显式还原后者
        sys.modules["modfetch.plugins.base"] = original_base
        setattr(modfetch.plugins, "base", original_base)


class TestPluginManager:
    def test_register_plugin_success(self):
        """注册成功：插件入表、handler 挂载、顺序记录"""
        manager = PluginManager()
        plugin = DummyPlugin()
        assert manager.register_plugin(plugin) is True
        assert manager.get_plugin("dummy") is plugin
        assert manager._hooks[HookType.CONFIG_LOADED] == [plugin.on_config_loaded]
        assert manager._hook_order[HookType.CONFIG_LOADED] == ["dummy"]

    def test_register_duplicate_plugin(self):
        """重复注册同名插件返回 False"""
        manager = PluginManager()
        assert manager.register_plugin(DummyPlugin()) is True
        assert manager.register_plugin(DummyPlugin()) is False

    async def test_register_plugin_with_config(self):
        """带配置注册：异步 initialize 被调度执行"""
        manager = PluginManager()
        plugin = DummyPlugin()
        assert manager.register_plugin(plugin, {"key": "value"}) is True
        # 让 asyncio.create_task 调度的 initialize 跑完
        await asyncio.sleep(0)
        assert plugin.config == {"key": "value"}

    def test_register_plugin_register_hooks_raises(self):
        """register_hooks 抛异常时注册失败返回 False"""

        class BoomPlugin(DummyPlugin):
            name = "boom"

            def register_hooks(self):
                raise RuntimeError("boom")

        manager = PluginManager()
        assert manager.register_plugin(BoomPlugin()) is False

    async def test_unregister_plugin(self):
        """卸载插件：handler 移除、插件出表"""
        manager = PluginManager()
        plugin = DummyPlugin()
        manager.register_plugin(plugin)
        assert manager.unregister_plugin("dummy") is True
        # 让 asyncio.create_task 调度的 shutdown 跑完，避免未等待协程警告
        await asyncio.sleep(0)
        assert manager.get_plugin("dummy") is None
        assert manager._hooks[HookType.CONFIG_LOADED] == []
        assert manager._hook_order[HookType.CONFIG_LOADED] == []

    def test_unregister_missing_plugin(self):
        """注销不存在的插件返回 False"""
        manager = PluginManager()
        assert manager.unregister_plugin("nope") is False

    def test_unregister_plugin_register_hooks_raises(self):
        """注销时 register_hooks 抛异常：返回 False 且插件保留"""

        class FlakyPlugin(DummyPlugin):
            name = "flaky"

            def __init__(self):
                super().__init__()
                self._calls = 0

            def register_hooks(self):
                self._calls += 1
                if self._calls > 1:
                    raise RuntimeError("boom")
                return {HookType.CONFIG_LOADED: self.on_config_loaded}

        manager = PluginManager()
        plugin = FlakyPlugin()
        assert manager.register_plugin(plugin) is True
        assert manager.unregister_plugin("flaky") is False
        # 卸载失败，插件仍在表中
        assert manager.get_plugin("flaky") is plugin

    async def test_execute_hook_empty(self):
        """无 handler 的 Hook 返回空列表"""
        manager = PluginManager()
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert results == []

    async def test_execute_hook_sync_handler(self):
        """同步 handler 正常执行"""
        manager = PluginManager()
        manager.register_plugin(DummyPlugin())
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert len(results) == 1
        assert results[0].success is True

    async def test_execute_hook_async_handler(self):
        """异步 handler 被 await 执行"""

        class AsyncPlugin(DummyPlugin):
            name = "async_plugin"

            # 覆盖为异步 handler：返回协程，基类声明为同步返回 HookResult
            async def on_config_loaded(self, context):  # type: ignore[reportIncompatibleMethodOverride]
                return HookResult(data="async")

        manager = PluginManager()
        manager.register_plugin(AsyncPlugin())
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert results[0].data == "async"

    async def test_execute_hook_none_result(self):
        """handler 返回 None 时规范化为默认 HookResult"""

        class NonePlugin(DummyPlugin):
            name = "none_plugin"

            # 覆盖为返回 None：验证 execute_hook 的 None 规范化
            def on_config_loaded(self, context):  # type: ignore[reportIncompatibleMethodOverride]
                return None

        manager = PluginManager()
        manager.register_plugin(NonePlugin())
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert results[0].success is True
        assert results[0].data is None

    async def test_execute_hook_raw_result(self):
        """handler 返回非 HookResult 时包装为 data"""

        class RawPlugin(DummyPlugin):
            name = "raw_plugin"

            # 覆盖为返回裸值：验证 execute_hook 包装为 HookResult(data=...)
            def on_config_loaded(self, context):  # type: ignore[reportIncompatibleMethodOverride]
                return "raw-data"

        manager = PluginManager()
        manager.register_plugin(RawPlugin())
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert results[0].data == "raw-data"

    async def test_execute_hook_should_stop(self):
        """should_stop=True 中断后续 handler"""

        class StopPlugin(DummyPlugin):
            name = "stop_plugin"

            def on_config_loaded(self, context):
                return HookResult(should_stop=True)

        manager = PluginManager()
        manager.register_plugin(StopPlugin())
        manager.register_plugin(DummyPlugin())
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert len(results) == 1
        assert results[0].should_stop is True

    async def test_execute_hook_exception(self):
        """handler 抛异常时返回失败 HookResult 且不中断后续"""

        class BoomPlugin(DummyPlugin):
            name = "boom_plugin"

            def on_config_loaded(self, context):
                raise ValueError("boom")

        manager = PluginManager()
        manager.register_plugin(BoomPlugin())
        manager.register_plugin(DummyPlugin())
        results = await manager.execute_hook(
            HookType.CONFIG_LOADED, HookContext(config=_make_config())
        )
        assert len(results) == 2
        assert results[0].success is False
        assert results[0].error == "boom"
        assert results[1].success is True

    def test_get_plugin(self):
        """get_plugin 返回实例或 None"""
        manager = PluginManager()
        plugin = DummyPlugin()
        manager.register_plugin(plugin)
        assert manager.get_plugin("dummy") is plugin
        assert manager.get_plugin("nope") is None

    def test_list_plugins(self):
        """list_plugins 返回元数据摘要"""
        manager = PluginManager()
        manager.register_plugin(DummyPlugin())
        assert manager.list_plugins() == [
            {
                "name": "dummy",
                "version": "1.0.0",
                "description": "dummy plugin",
                "author": "test",
                "enabled": True,
            }
        ]

    def test_enable_disable_plugin(self):
        """enable/disable 切换插件启用状态"""
        manager = PluginManager()
        manager.register_plugin(DummyPlugin())
        assert manager.disable_plugin("dummy") is True
        plugin = manager.get_plugin("dummy")
        assert plugin is not None
        assert plugin.enabled is False
        assert manager.enable_plugin("dummy") is True
        assert plugin.enabled is True

    def test_enable_disable_missing_plugin(self):
        """enable/disable 不存在的插件返回 False"""
        manager = PluginManager()
        assert manager.enable_plugin("nope") is False
        assert manager.disable_plugin("nope") is False