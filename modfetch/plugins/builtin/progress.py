"""
进度显示内置插件

在下载过程中显示进度信息。
"""

from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class ProgressPlugin(ModFetchPlugin):
    """
    下载进度显示插件

    在下载过程中显示进度信息。
    """

    name = "progress"
    version = "1.0.0"
    description = "显示下载进度信息"
    author = "ModFetch"

    def __init__(self):
        super().__init__()
        self._download_count = 0
        self._completed_count = 0
        self._failed_count = 0

    def register_hooks(self):
        """注册 Hook 处理器"""
        return {
            HookType.PRE_DOWNLOAD: self.on_pre_download,
            HookType.POST_DOWNLOAD: self.on_post_download,
            HookType.DOWNLOAD_FAILED: self.on_download_failed,
        }

    def on_pre_download(self, context: HookContext) -> HookResult:
        """下载开始前"""
        self._download_count = 0
        self._completed_count = 0
        self._failed_count = 0
        print("📦 开始下载...")
        return HookResult()

    def on_post_download(self, context: HookContext) -> HookResult:
        """下载完成"""
        self._completed_count += 1
        print(f"✓ 下载完成 ({self._completed_count}/{self._download_count})")
        return HookResult()

    def on_download_failed(self, context: HookContext) -> HookResult:
        """下载失败"""
        self._failed_count += 1
        download_info = context.download_info
        if download_info:
            filename = download_info.get("filename", "unknown")
            print(f"✗ 下载失败: {filename}")
        return HookResult()


# 插件入口点
plugin_class = ProgressPlugin
