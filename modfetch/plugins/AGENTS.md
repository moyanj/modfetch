# MODFETCH PLUGINS (Python/Lua)

插件扩展系统：支持 Python 与 Lua 两种语言，按文件后缀分发到对应 loader。
位于包内但**不属于 hexagonal 任何一层**——是跨切面的扩展机制（hook 注入）。

## STRUCTURE
```
plugins/
├── base.py        # 插件接口: ModFetchPlugin / PluginManager / HookType / HookContext / HookResult
├── loader.py      # Python 插件加载器 (scan_directory / load_from_path / load_from_module)
├── lua_loader.py  # Lua 插件加载器 (initialize / shutdown / load_from_path / scan_directory)
├── lua_runtime.py # ⚠️ 全仓最大文件 (930 行): lupa Lua 桥接 + LuaPluginWrapper + LuaRuntimeManager
└── builtin/       # 内置插件: filter / progress / notify
```

## HOOK 生命周期（base.py HookType）
配置阶段: `CONFIG_LOADED` → `CONFIG_VALIDATED`
解析阶段: `PRE_RESOLVE` → `POST_RESOLVE` → `PRE_RESOLVE_DEPENDENCIES` → `POST_RESOLVE_DEPENDENCIES`
下载阶段: `PRE_DOWNLOAD` → `DOWNLOAD_PROGRESS` → `POST_DOWNLOAD` / `DOWNLOAD_FAILED`
打包阶段: `PRE_PACKAGE` → `POST_PACKAGE`
生命周期: `PLUGIN_LOAD` / `PLUGIN_UNLOAD`

## KEY PATTERNS
- **语言分发**（cli.py）: `.lua` → `LuaPluginLoader`，其余 → `PluginLoader`；目录扫描合并两个 `scan_directory` 结果
- `LuaPluginLoader` 需 `await initialize()` 启动运行时、`await shutdown()` 释放（try/finally 保证）
- `_validate_plugin_source`（loader.py）: 唯一 AST 检查——扫描危险导入（os.system/subprocess/eval/exec/...），命中仅 warning 不阻断
- 加载失败: Python loader 抛 `PluginLoadError`；CLI 层捕获后 logger 记录，不中断整个流程

## CONVENTIONS
- Python 插件类必须继承 `ModFetchPlugin` 并实现 `register_hooks()`
- Lua 插件是纯数据表 + 钩子函数（见 examples/plugins/*.lua）
- 插件加载失败降级为 warning（CLI 目录扫描）或 error（显式 --plugin）

## ANTI-PATTERNS
- 在插件中调用危险系统 API（os.system/subprocess/eval）——AST 检查会警告
- 忘记 `lua_plugin_manager.shutdown()`（try/finally 包裹）
- 在 domain 层使用插件系统（plugins 依赖 domain.config_models，方向相反）

## GOTCHAS
- `lua_runtime.py` 是全仓复杂度峰值：改它之前先跑插件相关测试
- `lua_loader.py` 有 3 处裸 `# type: ignore`（Lua 插件适配器属性签名），尽量带错误码