"""内置插件（builtin/filter.py、notify.py、progress.py）单元测试

用合成领域事件驱动各插件，断言过滤/通知/进度行为。
全部离线：不发送真实通知，仅验证 Hook 返回值与内部状态。
"""

import time

from modfetch.domain.config_models import ModEntry, ModFetchConfig
from modfetch.plugins.base import HookContext, HookResult, HookType
from modfetch.plugins.builtin.filter import FilterPlugin
from modfetch.plugins.builtin.notify import NotifyPlugin
from modfetch.plugins.builtin.progress import ProgressPlugin


def _make_context(**kwargs) -> HookContext:
    """构造最小合法 HookContext，kwargs 覆盖可选字段"""
    config = ModFetchConfig.from_dict(
        {"minecraft": {"version": ["1.21.1"], "mods": ["sodium"]}}
    )
    return HookContext(config=config, **kwargs)


class TestFilterPlugin:
    def test_plugin_class_entry(self):
        """模块级 plugin_class 指向 FilterPlugin"""
        from modfetch.plugins.builtin.filter import plugin_class

        assert plugin_class is FilterPlugin

    async def test_initialize_loads_blacklist(self):
        """初始化时黑名单统一转小写"""
        plugin = FilterPlugin()
        await plugin.initialize({"blacklist": ["Sodium", "IRIS"]})
        assert plugin._blacklist == {"sodium", "iris"}

    async def test_initialize_empty_blacklist(self):
        """无黑名单配置时为空集合"""
        plugin = FilterPlugin()
        await plugin.initialize({})
        assert plugin._blacklist == set()

    def test_register_hooks(self):
        """订阅 PRE_RESOLVE"""
        plugin = FilterPlugin()
        assert plugin.register_hooks() == {
            HookType.PRE_RESOLVE: plugin.on_pre_resolve
        }

    def test_blocks_by_id(self):
        """模组 id 命中黑名单 → should_stop"""
        plugin = FilterPlugin()
        plugin._blacklist = {"sodium"}
        context = _make_context(mod_entry=ModEntry(id="SODIUM"))
        result = plugin.on_pre_resolve(context)
        assert result.success is False
        assert result.should_stop is True

    def test_blocks_by_slug(self):
        """模组 slug 命中黑名单 → should_stop"""
        plugin = FilterPlugin()
        plugin._blacklist = {"sodium"}
        context = _make_context(mod_entry=ModEntry(slug="sodium"))
        result = plugin.on_pre_resolve(context)
        assert result.should_stop is True

    def test_allows_non_blacklisted(self):
        """未命中黑名单 → 正常放行"""
        plugin = FilterPlugin()
        plugin._blacklist = {"sodium"}
        context = _make_context(mod_entry=ModEntry(id="fabric-api"))
        result = plugin.on_pre_resolve(context)
        assert result.success is True
        assert result.should_stop is False

    def test_non_mod_entry(self):
        """mod_entry 非 ModEntry 时直接放行"""
        plugin = FilterPlugin()
        context = _make_context(mod_entry="not-a-mod-entry")
        result = plugin.on_pre_resolve(context)
        assert result.success is True


class TestNotifyPlugin:
    def test_plugin_class_entry(self):
        """模块级 plugin_class 指向 NotifyPlugin"""
        from modfetch.plugins.builtin.notify import plugin_class

        assert plugin_class is NotifyPlugin

    def test_register_hooks(self):
        """订阅 CONFIG_LOADED 与 POST_PACKAGE"""
        plugin = NotifyPlugin()
        assert plugin.register_hooks() == {
            HookType.CONFIG_LOADED: plugin.on_config_loaded,
            HookType.POST_PACKAGE: plugin.on_post_package,
        }

    def test_on_config_loaded_records_start_time(self):
        """CONFIG_LOADED 记录开始时间"""
        plugin = NotifyPlugin()
        result = plugin.on_config_loaded(_make_context())
        assert result.success is True
        assert plugin._start_time is not None

    def test_on_post_package_with_start_time(self):
        """有开始时间时计算耗时并返回成功"""
        plugin = NotifyPlugin()
        plugin._start_time = time.time() - 5
        context = _make_context()
        context.extra_data = {"output_path": "/tmp/out", "format": "mrpack"}
        result = plugin.on_post_package(context)
        assert result.success is True

    def test_on_post_package_without_start_time(self):
        """无开始时间时耗时按 0 处理"""
        plugin = NotifyPlugin()
        context = _make_context()
        result = plugin.on_post_package(context)
        assert result.success is True

    def test_on_post_package_default_extra_data(self):
        """extra_data 缺省时使用默认值"""
        plugin = NotifyPlugin()
        plugin._start_time = time.time()
        result = plugin.on_post_package(_make_context())
        assert result.success is True


class TestProgressPlugin:
    def test_plugin_class_entry(self):
        """模块级 plugin_class 指向 ProgressPlugin"""
        from modfetch.plugins.builtin.progress import plugin_class

        assert plugin_class is ProgressPlugin

    def test_register_hooks(self):
        """订阅下载阶段三个 Hook"""
        plugin = ProgressPlugin()
        assert plugin.register_hooks() == {
            HookType.PRE_DOWNLOAD: plugin.on_pre_download,
            HookType.POST_DOWNLOAD: plugin.on_post_download,
            HookType.DOWNLOAD_FAILED: plugin.on_download_failed,
        }

    def test_on_pre_download_resets(self):
        """下载开始前重置计数"""
        plugin = ProgressPlugin()
        plugin._download_count = 5
        plugin._completed_count = 3
        plugin._failed_count = 1
        result = plugin.on_pre_download(_make_context())
        assert result.success is True
        assert plugin._download_count == 0
        assert plugin._completed_count == 0
        assert plugin._failed_count == 0

    def test_on_post_download_increments(self):
        """下载完成成功计数 +1"""
        plugin = ProgressPlugin()
        plugin._download_count = 3
        result = plugin.on_post_download(_make_context())
        assert result.success is True
        assert plugin._completed_count == 1

    def test_on_download_failed_with_info(self):
        """下载失败失败计数 +1（含文件名信息）"""
        plugin = ProgressPlugin()
        context = _make_context(download_info={"filename": "bad.jar"})
        result = plugin.on_download_failed(context)
        assert result.success is True
        assert plugin._failed_count == 1

    def test_on_download_failed_without_info(self):
        """下载失败但无 download_info 时仍计数"""
        plugin = ProgressPlugin()
        context = _make_context(download_info=None)
        result = plugin.on_download_failed(context)
        assert result.success is True
        assert plugin._failed_count == 1