# ModFetch

[![PyPI version](https://img.shields.io/pypi/v/modfetch)](https://pypi.org/project/modfetch)
[![License: MIT](https://img.shields.io/github/license/yourname/modfetch)](https://github.com/yourname/modfetch)

ModFetch 是一个现代化的 Minecraft 模组打包和下载管理工具，支持从 Modrinth 等平台自动下载模组及其依赖项。

## 🌟 功能特性
- 支持多种配置格式（TOML/YAML/JSON/XML）
- 自动处理模组依赖关系
- 多线程下载加速
- 支持生成标准 `.mrpack` 整合包
- 支持 Forge/Fabric/NeoForge/Quilt 模组加载器（支持同时构建多个）
- 完整的配置继承机制

## 📦 安装指南
```bash
pip install modfetch
```

## 🚀 快速开始
```toml
# 示例配置文件 mods.toml
[minecraft]
version = ["1.21.1"]
mod_loader = ["fabric", "forge"] # 支持同时构建多个加载器
mods = [
    { id = "sodium", feature = "performance" },
    "modmenu"
]

[output]
download_dir = "./downloads"
format = ["mrpack"]
```

```bash
modfetch -c mods.toml
```

## 📁 项目结构
```
modfetch
├── README.md
├── config.py       # 配置解析模块
├── core.py         # 核心下载逻辑
├── api.py          # Modrinth API 接口
└── pyproject.toml  # 项目配置
```

## 🤝 贡献指南
欢迎提交 PR 和报告 issue。请遵循 [CONTRIBUTING.md] 指南。

## 📄 许可证
MIT License - [LICENSE](LICENSE) 文件