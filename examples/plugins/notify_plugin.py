"""
通知插件示例

展示如何使用 POST_PACKAGE Hook 来发送通知。
"""

import asyncio
from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class NotifyPlugin(ModFetchPlugin):
    """
    打包完成通知插件

    在打包完成后发送桌面通知。
    """

    name = "notify"
    version = "1.0.0"
    description = "打包完成通知"
    author = "ModFetch"

    def __init__(self):
        super().__init__()
        self._start_time = None

    def register_hooks(self) -> dict:
        """注册 Hook 处理器"""
        return {
            HookType.CONFIG_LOADED: self.on_config_loaded,
            HookType.POST_PACKAGE: self.on_post_package,
        }

    def on_config_loaded(self, context: HookContext) -> HookResult:
        """记录开始时间"""
        import time

        self._start_time = time.time()
        return HookResult()

    def on_post_package(self, context: HookContext) -> HookResult:
        """打包完成后发送通知"""
        import time

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

        # 尝试发送桌面通知
        self._send_notification(f"ModFetch 打包完成", f"{format_type} 包已生成")

        return HookResult()

    def _send_notification(self, title: str, message: str) -> None:
        """发送桌面通知"""
        try:
            # 尝试使用 notify2 (Linux)
            import notify2

            notify2.init("ModFetch")
            notification = notify2.Notification(title, message)
            notification.show()
        except ImportError:
            pass

        try:
            # 尝试使用 plyer (跨平台)
            from plyer import notification

            notification.notify(
                title=title,
                message=message,
                app_name="ModFetch",
                timeout=5,
            )
        except ImportError:
            pass


# 插件入口点
plugin_class = NotifyPlugin
