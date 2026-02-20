"""
进度显示插件示例

展示如何使用 DOWNLOAD_PROGRESS Hook 来显示下载进度。
"""

from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class ProgressPlugin(ModFetchPlugin):
    """
    下载进度显示插件

    在下载过程中显示进度条。
    """

    name = "progress_display"
    version = "1.0.0"
    description = "显示下载进度"
    author = "ModFetch"

    def __init__(self):
        super().__init__()
        self._download_stats = {
            "total": 0,
            "completed": 0,
            "failed": 0,
        }

    def register_hooks(self) -> dict:
        """注册 Hook 处理器"""
        return {
            HookType.PRE_DOWNLOAD: self.on_pre_download,
            HookType.DOWNLOAD_PROGRESS: self.on_download_progress,
            HookType.POST_DOWNLOAD: self.on_post_download,
            HookType.DOWNLOAD_FAILED: self.on_download_failed,
        }

    def on_pre_download(self, context: HookContext) -> HookResult:
        """下载开始前"""
        self._download_stats = {
            "total": 0,
            "completed": 0,
            "failed": 0,
        }
        print("📦 开始下载...")
        return HookResult()

    def on_download_progress(self, context: HookContext) -> HookResult:
        """下载进度更新"""
        download_info = context.download_info
        if download_info:
            filename = download_info.get("filename", "unknown")
            percent = download_info.get("percent", 0)
            size = download_info.get("size", 0)
            downloaded = download_info.get("downloaded", 0)

            # 简单的进度显示
            bar_length = 30
            filled = int(bar_length * percent / 100)
            bar = "█" * filled + "░" * (bar_length - filled)

            print(
                f"\r{filename}: [{bar}] {percent:.1f}% ({downloaded}/{size} bytes)",
                end="",
                flush=True,
            )

        return HookResult()

    def on_post_download(self, context: HookContext) -> HookResult:
        """下载完成"""
        self._download_stats["completed"] += 1
        print()  # 换行
        return HookResult()

    def on_download_failed(self, context: HookContext) -> HookResult:
        """下载失败"""
        self._download_stats["failed"] += 1
        download_info = context.download_info
        if download_info:
            filename = download_info.get("filename", "unknown")
            print(f"\n❌ 下载失败: {filename}")
        return HookResult()


# 插件入口点
plugin_class = ProgressPlugin
