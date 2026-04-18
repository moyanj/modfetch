# ModFetch

[![PyPI version](https://img.shields.io/pypi/v/modfetch)](https://pypi.org/project/modfetch)
[![License: MIT](https://img.shields.io/github/license/moyanj/modfetch)](https://github.com/moyanj/modfetch)

ModFetch 是一个现代化的 Minecraft 模组打包和下载管理工具，支持从 Modrinth 自动下载模组及其依赖项，生成标准 `.mrpack` 整合包。

## 🌟 功能特性

- **多平台支持**: 支持 Windows、Linux、macOS
- **多加载器**: 同时支持 Forge、Fabric、NeoForge、Quilt
- **多版本构建**: 一次配置，同时构建多个 Minecraft 版本
- **自动依赖解析**: 自动下载模组的所有依赖
- **多格式输出**: 支持 `.mrpack` 标准格式和 `.zip` 格式
- **配置继承**: 支持从 URL 或本地文件继承配置
- **插件系统**: 支持 Python 和 Lua 插件扩展功能
- **多配置格式**: 支持 TOML、YAML、JSON 配置文件

## 📦 安装

### 通过 pip 安装

```bash
pip install modfetch
```

### 使用预编译二进制文件

从 [GitHub Releases](https://github.com/moyanj/modfetch/releases) 下载对应平台的可执行文件。

## 🚀 快速开始

### 1. 创建配置文件

创建 `mods.toml`:

```toml
[minecraft]
version = ["1.21.1"]
mod_loader = ["fabric"]  # 支持 ["fabric", "forge"] 同时构建多个
mods = [
    "sodium",
    "modmenu",
    { id = "iris", feature = "graphics" },
]

[output]
download_dir = "./downloads"
format = ["mrpack", "zip"]

[metadata]
name = "My Awesome Modpack"
version = "1.0.0"
description = "A modpack created with ModFetch"
```

### 2. 运行

```bash
modfetch mods.toml
```

## 📖 配置详解

### 基础配置

```toml
[minecraft]
# Minecraft 版本列表（支持多版本同时构建）
version = ["1.21.1", "1.20.4"]

# 模组加载器（支持多个）
mod_loader = ["fabric", "forge"]

# 模组列表
mods = [
    # 简单字符串形式
    "sodium",
    "modmenu",
    # 详细配置形式
    { id = "iris", feature = "graphics" },
    { slug = "sodium-extra", only_version = "1.21.1" },
]

# 资源包
resourcepacks = [
    "faithful",
]

# 光影包
shaderpacks = [
    "complementary-reimagined",
]

# 额外下载链接
extra_urls = [
    { url = "https://example.com/custom-file.jar", filename = "custom.jar" },
]
```

### 输出配置

```toml
[output]
# 下载目录
download_dir = "./downloads"

# 输出格式: "mrpack" | "zip"
format = ["mrpack"]

# mrpack 模式: "download"（下载到 overrides）| "reference"（仅引用）
mrpack_modes = ["download"]
```

### 插件配置

```toml
[plugins]
enabled = ["progress", "notify"]

[plugins.config.notify]
webhook_url = "https://example.com/webhook"
```

### 配置继承

支持从其他配置文件或 mrpack 继承：

```toml
# 从 URL 继承
from = { url = "https://example.com/base-config.toml", format = "toml" }

# 从多个来源继承
from = [
    { url = "./base.toml", format = "toml" },
    { url = "https://example.com/extra.yaml", format = "yaml" },
]
```

## 🔌 插件系统

ModFetch 支持 Python 和 Lua 两种插件语言。

### 使用内置插件

```bash
# 显示下载进度
modfetch mods.toml --plugin progress

# 完成后发送通知
modfetch mods.toml --plugin notify

# 使用多个插件
modfetch mods.toml --plugin progress --plugin notify
```

### 从文件加载插件

```bash
# Python 插件
modfetch mods.toml --plugin ./my_plugin.py

# Lua 插件
modfetch mods.toml --plugin ./my_plugin.lua
```

### 插件目录

```bash
modfetch mods.toml --plugin-dir ./plugins/
```

### 编写 Python 插件

```python
from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class MyPlugin(ModFetchPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "我的插件"
    author = "Your Name"

    def register_hooks(self) -> dict:
        return {
            HookType.POST_PACKAGE: self.on_post_package,
        }

    def on_post_package(self, context: HookContext) -> HookResult:
        print(f"打包完成: {context.output_path}")
        return HookResult()


plugin_class = MyPlugin
```

### 编写 Lua 插件

```lua
plugin = {
    name = "my_plugin",
    version = "1.0.0",
    description = "我的插件",
    author = "Your Name"
}

function on_post_package(context)
    modfetch.log("info", "打包完成: " .. context.output_path)
    return { success = true }
end
```

更多插件示例见 [examples/plugins/](examples/plugins/)。

## 🛠️ CLI 选项

```bash
modfetch [OPTIONS] CONFIG

选项:
  -f, --feature TEXT       启用的功能标签
  --plugin TEXT            加载插件（可多次使用）
  --plugin-dir TEXT        插件目录路径
  --list-plugins           列出已加载的插件
  --dry-run                干运行模式（只验证配置）
  --debug                  启用调试模式
  --version                显示版本
  --help                   显示帮助
```

## 📁 项目结构

```
modfetch/
├── modfetch/           # Python 后端
│   ├── cli.py         # 命令行接口
│   ├── orchestrator.py # 核心协调逻辑
│   ├── api/           # Modrinth API 封装
│   ├── download/      # 异步下载管理
│   ├── models/        # 数据模型
│   ├── services/      # 解析器服务
│   ├── packager/      # 打包器
│   └── plugins/       # 插件系统
├── modfetch-ui/       # Vue 3 前端（可选）
├── examples/          # 示例配置和插件
└── pyproject.toml     # 项目配置
```

## 🤝 贡献

欢迎提交 PR 和报告 issue！

## 📄 许可证

MIT License