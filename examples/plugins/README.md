# ModFetch 插件示例

这个目录包含 ModFetch 插件系统的示例插件，支持 Python 和 Lua 两种语言。

## 示例插件列表

### Python 插件

#### 1. progress_plugin.py - 进度显示插件

展示如何使用 `DOWNLOAD_PROGRESS` Hook 来显示下载进度。

```bash
modfetch -c mods.toml --plugin examples/plugins/progress_plugin.py
```

#### 2. filter_plugin.py - 模组过滤插件

展示如何使用 `PRE_RESOLVE` Hook 来过滤模组。

```bash
modfetch -c mods.toml --plugin examples/plugins/filter_plugin.py
```

#### 3. notify_plugin.py - 通知插件

展示如何使用 `POST_PACKAGE` Hook 在打包完成后发送通知。

```bash
modfetch -c mods.toml --plugin examples/plugins/notify_plugin.py
```

### Lua 插件

#### 1. hello.lua - Hello World 插件

基础的 Lua 插件示例，展示了所有可用的 Hook。

```bash
modfetch -c mods.toml --plugin examples/plugins/hello.lua
```

#### 2. filter.lua - 模组过滤插件

Lua 版本的模组过滤插件，演示如何根据配置过滤模组。

```bash
modfetch -c mods.toml --plugin examples/plugins/filter.lua
```

#### 3. stats.lua - 统计插件

收集并输出下载统计信息。

```bash
modfetch -c mods.toml --plugin examples/plugins/stats.lua
```

#### 4. file_operations.lua - 文件操作插件

演示文件系统 API 的使用。

```bash
modfetch -c mods.toml --plugin examples/plugins/file_operations.lua
```

#### 5. http_client.lua - HTTP 客户端插件

演示 HTTP 请求 API 的使用。

```bash
modfetch -c mods.toml --plugin examples/plugins/http_client.lua
```

#### 6. string_utils.lua - 字符串工具插件

演示字符串处理 API 的使用。

```bash
modfetch -c mods.toml --plugin examples/plugins/string_utils.lua
```

#### 7. crypto_utils.lua - 加密哈希工具插件

演示哈希和编码 API 的使用。

```bash
modfetch -c mods.toml --plugin examples/plugins/crypto_utils.lua
```

#### 8. path_utils.lua - 路径工具插件

演示路径和 URL 处理 API 的使用。

```bash
modfetch -c mods.toml --plugin examples/plugins/path_utils.lua
```

#### 10. modrinth_api.lua - Modrinth API 插件

演示如何使用 Modrinth API 查询模组信息。

```bash
modfetch -c mods.toml --plugin examples/plugins/modrinth_api.lua
```

#### 11. mod_search.lua - 模组搜索插件

演示如何使用 Modrinth API 搜索模组。

```bash
modfetch -c mods.toml --plugin examples/plugins/mod_search.lua
```

#### 12. loader_version.lua - 加载器版本查询插件

演示如何查询 Fabric/Forge/Quilt 加载器版本。

```bash
modfetch -c mods.toml --plugin examples/plugins/loader_version.lua
```

#### 13. config_inspector.lua - 配置检查器插件

演示如何使用配置 API 检查和操作配置。

```bash
modfetch -c mods.toml --plugin examples/plugins/config_inspector.lua
```

## 编写 Python 插件

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

## 编写 Lua 插件

1. 创建一个 `.lua` 文件
2. 定义 `plugin` 元数据表
3. 实现需要的 Hook 函数

### 基本结构

```lua
-- 插件元数据
plugin = {
    name = "my_plugin",
    version = "1.0.0",
    description = "我的插件",
    author = "Your Name"
}

-- 配置（由 Python 端传递）
-- plugin_config = {}

-- Hook 函数
function on_config_loaded(context)
    modfetch.log("info", "配置已加载")

    return {
        success = true
    }
end

function on_post_package(context)
    modfetch.log("info", "打包完成！")

    return {
        success = true
    }
end
```

### Lua 插件 API

Lua 插件可以通过 `modfetch` 全局表访问以下功能：

#### 日志
```lua
modfetch.log(level, message)
-- level: "debug", "info", "warning", "error"
```

#### JSON 处理
```lua
local json_str = modfetch.json_encode(data)
local data = modfetch.json_decode(json_str)
```

#### 字符串处理
```lua
-- 基础操作
local parts = modfetch.split(text, delimiter)
local trimmed = modfetch.trim(text)
local starts = modfetch.starts_with(text, prefix)
local ends = modfetch.ends_with(text, suffix)
local contains = modfetch.contains(text, substring)
local replaced = modfetch.replace(text, old, new)
local lower = modfetch.lower(text)
local upper = modfetch.upper(text)
local sub = modfetch.sub(text, start, end)

-- 正则匹配
local match = modfetch.match(text, pattern)
local all_matches = modfetch.match_all(text, pattern)
```

#### 文件系统
```lua
-- 文件操作
local exists = modfetch.file_exists(path)
local content = modfetch.file_read(path)
modfetch.file_write(path, content)
modfetch.file_append(path, content)
modfetch.file_delete(path)

-- 目录操作
local exists = modfetch.dir_exists(path)
modfetch.dir_create(path)
local files = modfetch.dir_list(path)

-- 路径操作
local joined = modfetch.path_join(base, ...)
local dirname = modfetch.path_dirname(path)
local basename = modfetch.path_basename(path)
local ext = modfetch.path_ext(path)
```

#### HTTP 请求
```lua
-- GET 请求
local response = modfetch.http_get(url, headers)
-- response: { status, text, headers, success, error }

-- POST 请求
local response = modfetch.http_post(url, data, headers)
-- data 可以是字符串或 table
```

#### URL 处理
```lua
local encoded = modfetch.url_encode(text)
local decoded = modfetch.url_decode(text)
local joined = modfetch.url_join(base, url)
local parsed = modfetch.url_parse(url)
-- parsed: { scheme, netloc, path, params, query, fragment }
```

#### 时间处理
```lua
local timestamp = modfetch.time_now()
local formatted = modfetch.time_format(timestamp, format)
-- format 默认: "%Y-%m-%d %H:%M:%S"

modfetch.sleep(seconds)
```

#### 哈希和编码
```lua
local md5 = modfetch.hash_md5(text)
local sha1 = modfetch.hash_sha1(text)
local sha256 = modfetch.hash_sha256(text)

local encoded = modfetch.base64_encode(text)
local decoded = modfetch.base64_decode(text)
```

#### 随机数
```lua
local int = modfetch.random_int(min, max)
local float = modfetch.random_float()  -- 0.0 ~ 1.0
local choice = modfetch.random_choice(items)
```

#### UUID
```lua
local uuid = modfetch.uuid()
```

#### Modrinth API（需要 ModrinthClient）
```lua
-- 获取项目信息
local result = modfetch.modrinth.get_project(project_id)
-- result: { success, id, name, title, description, project_type, versions }

-- 获取版本信息
local result = modfetch.modrinth.get_version(project_id, mc_version, mod_loader, specific_version)
-- result: { success, version, file }

-- 搜索模组
local result = modfetch.modrinth.search(query, facets, limit)
-- result: { success, hits, total }

-- 获取加载器版本
local result = modfetch.modrinth.get_loader_version(mc_version, loader)
-- loader: "fabric", "forge", "quilt"
-- result: { success, version }
```

#### 配置 API（需要 ModFetchConfig）
```lua
-- 获取完整配置
local config = modfetch.config.get()

-- 获取 Minecraft 配置
local mc_config = modfetch.config.get_minecraft()
-- mc_config: { version, mod_loader, mods }

-- 获取输出配置
local output_config = modfetch.config.get_output()
-- output_config: { download_dir, format }

-- 获取插件配置
local plugin_config = modfetch.config.get_plugin(plugin_name)

-- 获取所有模组列表
local mods = modfetch.config.get_mods()
-- mods: [ { id, slug }, ... ]
```

### Lua 可用的 Hook

- `on_plugin_load` - 插件加载时
- `on_plugin_unload` - 插件卸载时
- `on_config_loaded` - 配置加载完成后
- `on_config_validated` - 配置验证完成后
- `on_pre_resolve` - 开始解析模组前
- `on_post_resolve` - 解析模组完成后
- `on_pre_resolve_dependencies` - 开始解析依赖前
- `on_post_resolve_dependencies` - 解析依赖完成后
- `on_pre_download` - 开始下载前
- `on_download_progress` - 下载进度更新
- `on_post_download` - 下载完成后
- `on_download_failed` - 下载失败时
- `on_pre_package` - 开始打包前
- `on_post_package` - 打包完成后

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
# Python 插件
modfetch -c mods.toml --plugin /path/to/plugin.py

# Lua 插件
modfetch -c mods.toml --plugin /path/to/plugin.lua
```

### 从目录加载

```bash
modfetch -c mods.toml --plugin-dir /path/to/plugins/
```

### 加载多个插件

```bash
modfetch -c mods.toml \
  --plugin /path/to/plugin1.py \
  --plugin /path/to/plugin2.lua
```

## 配置文件中启用插件

在 `mods.toml` 中添加插件配置：

```toml
[plugins]
enabled = ["progress_display", "notify", "hello"]

[plugins.config.progress_display]
show_speed = true

[plugins.config.notify]
enabled = true

[plugins.config.hello]
greeting = "Hello from config!"
```
