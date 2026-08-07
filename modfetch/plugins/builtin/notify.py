"""
通知内置插件

在打包完成后发送通知。
"""

import time
from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class NotifyPlugin(ModFetchPlugin):
    """
    打包完成通知插件

    从 CONFIG_LOADED 开始计时，打包完成后（POST_PACKAGE）打印输出路径、
    格式与耗时。输出信息取自 context.extra_data（output_path / format）。
    """

    name = "notify"
    version = "1.0.0"
    description = "打包完成通知"
    author = "ModFetch"

    def __init__(self):
        super().__init__()
        self._start_time = None  # 构建开始时间戳（CONFIG_LOADED 时记录）

    def register_hooks(self):
        """注册 Hook 处理器（订阅配置加载与打包完成）"""
        return {
            HookType.CONFIG_LOADED: self.on_config_loaded,
            HookType.POST_PACKAGE: self.on_post_package,
        }

    def on_config_loaded(self, context: HookContext) -> HookResult:
        """记录开始时间（用于计算整体打包耗时）"""
        self._start_time = time.time()
        return HookResult()

    def on_post_package(self, context: HookContext) -> HookResult:
        """
        打包完成后发送通知

        从 context.extra_data 读取输出路径与格式，计算从 CONFIG_LOADED
        到打包完成的耗时并打印汇总。
        """
        output_path = context.extra_data.get("output_path", "")
        format_type = context.extra_data.get("format", "unknown")

        # 计算耗时
        elapsed = 0
        if self._start_time:
            elapsed = time.time() - self._start_time

        print(f"\n🎉 打包完成!")
        print(f"   格式: {format_type}")
        print(f"   路径: {output_path}")
        print(f"   耗时: {elapsed:.2f}秒")

        return HookResult()


# 插件入口点
plugin_class = NotifyPlugin
