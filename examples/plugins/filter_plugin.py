"""
模组过滤插件示例

展示如何使用 PRE_RESOLVE Hook 来过滤模组。
"""

from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class FilterPlugin(ModFetchPlugin):
    """
    模组过滤插件

    根据黑名单过滤模组。
    """

    name = "mod_filter"
    version = "1.0.0"
    description = "根据黑名单过滤模组"
    author = "ModFetch"

    def __init__(self):
        super().__init__()
        self._blacklist = set()

    async def initialize(self, config: dict) -> None:
        """初始化插件，加载黑名单"""
        await super().initialize(config)

        # 从配置中读取黑名单
        blacklist = config.get("blacklist", [])
        self._blacklist = set(name.lower() for name in blacklist)

        if self._blacklist:
            print(f"🚫 已加载黑名单: {', '.join(self._blacklist)}")

    def register_hooks(self) -> dict:
        """注册 Hook 处理器"""
        return {
            HookType.PRE_RESOLVE: self.on_pre_resolve,
        }

    def on_pre_resolve(self, context: HookContext) -> HookResult:
        """解析模组前检查黑名单"""
        from modfetch.domain.config_models import ModEntry

        mod_entry = context.mod_entry
        if isinstance(mod_entry, ModEntry):
            mod_id = (mod_entry.id or "").lower()
            mod_slug = (mod_entry.slug or "").lower()

            # 检查是否在黑名单中
            if mod_id in self._blacklist or mod_slug in self._blacklist:
                print(f"🚫 跳过黑名单模组: {mod_id or mod_slug}")
                return HookResult(success=False, should_stop=True)

        return HookResult()


# 插件入口点
plugin_class = FilterPlugin
