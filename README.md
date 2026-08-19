<div align="center">

<img src="logo/logo_raw.png" alt="ModFetch Logo" width="160" />

# ModFetch

**一份配置，一条命令，为所有 Minecraft 版本 × 加载器构建整合包。**

[![Build and Test](https://github.com/moyanj/modfetch/actions/workflows/build.yml/badge.svg)](https://github.com/moyanj/modfetch/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/moyanj/modfetch)](https://github.com/moyanj/modfetch/releases)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[快速开始](#-快速开始) · [功能一览](#-为什么选择-modfetch) · [配置文档](docs.md) · [示例](examples/)

</div>

---

## 😖 你是不是也这样？

每次 Minecraft 更新，维护整合包都变成一场噩梦：

- 🔄 同一个整合包要维护 1.20.1 / 1.21.1 好几个版本，Fabric / NeoForge 还各来一份
- 🔍 逐个模组去 Modrinth 查「这个版本有没有更新」「依赖装全了没有」
- 📦 下载、整理目录、打包、重命名……每个组合重复一遍

**ModFetch 把这一切压缩成一条命令。** 你只需要在配置文件里列出模组名，剩下的——查版本、匹配加载器、解析依赖、并发下载、打包 `.mrpack` / `.zip`——全部自动完成。

```bash
modfetch build   # 完事。去 downloads/dist/ 拿整合包。
```

---

## ✨ 为什么选择 ModFetch

| 能力 | 说明 |
|---|---|
| 🚀 **一次构建，全平台覆盖** | 一份配置同时构建多个 MC 版本 × 多个加载器的整合包，矩阵式展开 |
| 🎯 **版本自动匹配** | 自动在 Modrinth 上为每个目标挑选兼容的模组版本，无需人工核对 |
| 🧩 **依赖自动解析** | 模组的依赖、依赖的依赖……自动补全，不再缺斤少两 |
| 📦 **三类内容通吃** | 模组 / 资源包 / 光影包统一配置；`extra_urls` 还能塞进任意本地文件或 URL |
| 🏷️ **条件化配置** | `only_version` + `only_loader` + `feature`，一套配置管理「多版本 / 多加载器 / 性能版·高清版·纯原版」多种形态 |
| 🧬 **配置继承** | `from` 继承本地文件、远程 URL、甚至现成的 `.mrpack`，公共部分只写一遍 |
| ⚡ **内容寻址缓存** | 全局缓存 + 硬链接复用，重复构建几乎零下载、零多余磁盘占用 |
| 🔌 **插件系统** | Python / Lua 插件挂接构建流程，进度展示、消息通知随你扩展 |
| 🖥️ **Web 管理界面** | 图形化编辑配置、搜索模组、实时查看下载与打包进度（🚧 开发中） |

### 打包格式

- **`.mrpack`**（Modrinth 标准格式）
  - `download` 模式：模组全部打进包里，**解压即玩**
  - `reference` 模式：只存引用清单，包体轻量，**适合分发**
- **`.zip`**：传统格式，兼容一切启动器

---

## ⚖️ 和同类工具比一下

| 能力 | **ModFetch** | [packwiz](https://packwiz.infra.link/) | Modrinth App | CurseForge App | Prism Launcher |
|---|---|---|---|---|---|
| 使用方式 | CLI（Web 界面开发中） | CLI | 桌面 GUI | 桌面 GUI | 启动器 GUI |
| 一次配置构建 **多版本 × 多加载器** | ✅ 矩阵式展开 | ❌ 一个包一个目标 | ❌ | ❌ | ❌ |
| 模组 / 资源包 / 光影包 | ✅ 三类统一 | ❌ 仅模组 | ⚠️ 仅模组 | ⚠️ 仅模组 | ⚠️ 仅模组 |
| 依赖自动解析 | ✅ | ✅ | ✅ | ⚠️ 部分 | ❌ |
| 条件化配置（feature / only_loader） | ✅ | ❌ | ❌ | ❌ | ❌ |
| 配置继承 / 模块化 | ✅ `from` 多级继承 | ⚠️ 仅导入 | ❌ | ❌ | ❌ |
| 内容寻址缓存复用 | ✅ | ❌ | ⚠️ | ⚠️ | ⚠️ |
| 插件扩展 | ✅ Python / Lua | ❌ | ❌ | ❌ | ❌ |
| 适配 **Modrinth** | ✅ | ✅ | ✅ | ❌ | ⚠️ |
| 适配 **CurseForge** | ❌ | ✅ | ❌ | ✅ | ⚠️ |
| 产出 `.mrpack` | ✅ download / reference | ✅ | ✅ | ❌ | ✅ |
| 产出 CF `.zip` | ✅ | ✅ | ❌ | ✅ | ✅ |
| 脚本化 / CI 集成 | ✅ | ✅ | ❌ | ❌ | ❌ |

> 同类工具各有侧重：packwiz 适合极简命令式管理，Modrinth / CurseForge App 适合玩家点装，Prism 适合日常游戏启动——但
> **没有一个是「面向整合包维护者」的自动化流水线**。ModFetch 的定位，就是把「多版本 × 多加载器 × 多形态」的矩阵构建变成一条命令。

### 什么时候不需要 ModFetch？

- 只想给自己装几个模组玩 → 用 Modrinth App / Prism Launcher 更快
- 只维护一个版本、一个加载器 → packwiz 够用
- 需要多版本矩阵构建、条件化配置、自动依赖、能接 CI —— 这就是 ModFetch 的主场 🐋

---

## 🚀 快速开始

需要 **Python 3.10+**，推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv pip install modfetch
```

写一份配置（更多示例见 [`examples/`](examples/)）：

```toml
# mods.toml
[metadata]
name = "我的整合包"
version = "1.0.0"
description = "简单又好用"

[minecraft]
version = ["1.21.1"]           # 想覆盖几个版本就写几个
mod_loader = "fabric"           # fabric / forge / neoforge / quilt

mods = [
    "sodium",
    "modmenu",
    "fabric-api",
]

[output]
download_dir = "./downloads"
format = ["mrpack", "zip"]      # .mrpack 和 .zip 一起出
```

一条命令，开始构建：

```bash
uv run modfetch build             # 使用当前目录 mods.toml 构建
uv run modfetch build -c other.toml   # 指定其他配置文件
```

完成后，整合包就在 `./downloads/dist/` 里等你。🎉

> 💡 其他命令：`modfetch check` 只校验不下载 · `modfetch plan -o plan.json` 生成构建计划 ·
> `-f <feature>` 切换功能形态 · `modfetch search <关键词>` 在 Modrinth 搜索模组（支持 `--type`/`--mc-version`/`--loader` 过滤）·
> `modfetch add <关键词>` 搜索并加入 `mods.toml`（交互选择或 `--yes` 直取第一条，保留配置注释）·
> `modfetch clean --cache` 清理下载缓存

---

## 🖥️ Web 界面

> 🚧 **状态：开发中（WIP）**
>
> Web 管理界面**尚未开发完成**，目前仅用于开发预览，可能存在功能缺失与不稳定问题，**暂不建议生产使用**。
> 日常使用请优先走 CLI 方式（见上方「快速开始」）。
>
> **规划中的能力**：
> - 📝 图形化编辑构建配置
> - 🔎 直接搜索 Modrinth 模组，一键加入列表
> - 📊 实时查看每个模组的下载状态与整体打包进度

后端服务（开发预览）：

```bash
uv run python -m modfetch.server    # 默认监听 0.0.0.0:8000
```

前端开发模式（需 Node + pnpm）：

```bash
cd web && pnpm install && pnpm dev
```

生产部署：先 `pnpm build`，后端会自动挂载 `web/dist`。

---

## 🔌 插件

支持 **Python** 与 **Lua** 插件，通过 `--plugin` / `--plugin-dir` 或配置里的 `[plugins]` 加载，挂接构建流程实现进度展示、完成通知等自定义行为。示例见 [`examples/plugins/`](examples/plugins/)。

---

## 📖 配置详解

配置支持 `toml` / `yaml` / `json`（推荐 `toml`）。字段说明、条件编译规则、配置继承与合并逻辑，全部在 **[配置格式规范文档](docs.md)** 里。

三条小贴士：

- 模组只需填 **Modrinth 项目 ID 或 slug**，无需其他信息
- 使用光影包时，记得在 `mods` 里加上光影加载器（`iris` / `oculus` / `optifine` 之一）
- 复杂配置建议拆文件，用 `from` 继承组织

---

## 🛠️ 开发

```bash
uv run pytest            # 测试（完全离线）
uv run nuitka_build.py   # Nuitka 打包为单文件可执行程序 modfetch.bin
```

## 🤝 参与贡献

欢迎 Issue 与 PR！无论是功能建议、Bug 报告还是文档改进，都非常感谢。

如果这个项目帮到了你，请给它一个 ⭐ Star —— 这是最大的鼓励！

## 许可证

[MIT](LICENSE)
