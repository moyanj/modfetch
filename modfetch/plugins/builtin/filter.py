"""
模组过滤内置插件

根据黑名单过滤模组。
"""

from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class FilterPlugin(ModFetchPlugin):
    """
    模组过滤插件

    在解析阶段（PRE_RESOLVE）根据黑名单过滤模组：命中黑名单的模组
    返回 should_stop=True 以跳过后续处理。
    """

    name = "filter"
    version = "1.0.0"
    description = "根据黑名单过滤模组"
    author = "ModFetch"

    def __init__(self):
        super().__init__()
        self._blacklist = set()  # 小写化的黑名单集合，用于 O(1) 命中判断

    async def initialize(self, config: dict) -> None:
        """初始化插件，加载黑名单"""
        await super().initialize(config)

        # 从配置中读取黑名单
        blacklist = config.get("blacklist", [])
        # 统一转小写，保证与模组 ID/slug 的比较大小写不敏感
        self._blacklist = set(name.lower() for name in blacklist)

        if self._blacklist:
            print(f"🚫 已加载黑名单: {', '.join(self._blacklist)}")

    def register_hooks(self):
        """注册 Hook 处理器（订阅解析前阶段）"""
        return {
            HookType.PRE_RESOLVE: self.on_pre_resolve,
        }

    def on_pre_resolve(self, context: HookContext) -> HookResult:
        """
        解析模组前检查黑名单

        若当前模组的 id 或 slug 命中黑名单，返回 should_stop=True 阻止其进入解析流程。
        """
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
