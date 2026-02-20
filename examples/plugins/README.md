# ModFetch 插件示例

这个目录包含 ModFetch 插件系统的示例插件。

## 示例插件列表

### 1. progress_plugin.py - 进度显示插件

展示如何使用 `DOWNLOAD_PROGRESS` Hook 来显示下载进度。

```bash
modfetch -c mods.toml --plugin examples/plugins/progress_plugin.py
```

### 2. filter_plugin.py - 模组过滤插件

展示如何使用 `PRE_RESOLVE` Hook 来过滤模组。

```bash
modfetch -c mods.toml --plugin examples/plugins/filter_plugin.py
```

### 3. notify_plugin.py - 通知插件

展示如何使用 `POST_PACKAGE` Hook 在打包完成后发送通知。

```bash
modfetch -c mods.toml --plugin examples/plugins/notify_plugin.py
```

## 编写自己的插件

1. 创建一个 Python 文件
2. 继承 `ModFetchPlugin` 类
3. 实现 `register_hooks()` 方法
4. 实现需要的 Hook 处理方法

### 基本结构

```python
from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class MyPlugin(ModFetchPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "我的插件"
    author = "Your Name"

    def register_hooks(self) -> dict:
        return {
            HookType.CONFIG_LOADED: self.on_config_loaded,
            HookType.POST_PACKAGE: self.on_post_package,
        }

    def on_config_loaded(self, context: HookContext) -> HookResult:
        # 处理配置加载
        return HookResult()

    def on_post_package(self, context: HookContext) -> HookResult:
        # 处理打包完成
        return HookResult()


plugin_class = MyPlugin
```

## 可用的 Hook 类型

- `CONFIG_LOADED` - 配置加载完成后
- `CONFIG_VALIDATED` - 配置验证完成后
- `PRE_RESOLVE` - 开始解析模组前
- `POST_RESOLVE` - 解析模组完成后
- `PRE_RESOLVE_DEPENDENCIES` - 开始解析依赖前
- `POST_RESOLVE_DEPENDENCIES` - 解析依赖完成后
- `PRE_DOWNLOAD` - 开始下载前
- `DOWNLOAD_PROGRESS` - 下载进度更新
- `POST_DOWNLOAD` - 下载完成后
- `DOWNLOAD_FAILED` - 下载失败时
- `PRE_PACKAGE` - 开始打包前
- `POST_PACKAGE` - 打包完成后

## 加载插件

### 从文件加载

```bash
modfetch -c mods.toml --plugin /path/to/plugin.py
```

### 从目录加载

```bash
modfetch -c mods.toml --plugin-dir /path/to/plugins/
```

### 加载多个插件

```bash
modfetch -c mods.toml \
  --plugin /path/to/plugin1.py \
  --plugin /path/to/plugin2.py
```

## 配置文件中启用插件

在 `mods.toml` 中添加插件配置：

```toml
[plugins]
enabled = ["progress_display", "notify"]

[plugins.config.progress_display]
show_speed = true

[plugins.config.notify]
enabled = true
```
