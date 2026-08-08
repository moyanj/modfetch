# **ModFetch 配置格式规范文档**

ModFetch 旨在提供灵活的配置支持，支持 `toml`、`yaml`、`json` 三种格式。
**默认推荐使用 `.toml` 格式，因其易于阅读和编写的特性。**

---

## 📚 总览

整个配置文件为一个嵌套结构的字典，可包含以下主要部分：

| **配置节**    | **描述**                                                     |
| ------------- | ------------------------------------------------------------ |
| `[from]`      | 用于指定远程或本地的父配置文件并继承其内容                   |
| `[metadata]`  | 包含整合包的元数据，用于 `.mrpack` 自描述格式                |
| `[minecraft]` | Minecraft 相关设置（版本、模组加载器、模组/资源包/光影包等） |
| `[output]`    | 指定最终输出路径及后处理方式                                 |
| `[plugins]`   | 声明要启用的插件及插件配置                                   |
| `max_concurrent` | 最大并发下载数（整数，默认 5）                             |
| `max_retries` | 下载失败时的最大重试次数（整数，默认 3）                    |
| `retry_delay` | 重试之间的初始延迟时间（秒，默认 1.0）                      |
| `verify_ssl`  | 是否校验 TLS 证书（默认 `true`）                            |
| `features`    | 启用功能列表，用于匹配条目的 `feature` 条件（条件编译）     |

---

## 🔧 配置字段详解

### 1. `from` —— 配置源继承

允许从本地路径或远程 URL 加载并继承其他配置文件。支持指定多个配置源，
也支持以 `.mrpack` 文件作为父配置（将其 manifest 解析为配置）。

#### **字段说明**

- `url`：配置文件的位置，支持 `file://`（本地路径）、`http(s)://`（远程地址）
- `format`：文件格式，默认为 `toml`，支持 `json`、`yaml`、`toml`，以及 `mrpack`

#### **合并规则**

- 多个父配置从左到右叠加，最终以当前配置覆盖
- `dict` 值递归合并；`list` 值拼接去重（保持顺序）
- 其他标量值以当前配置（子配置）覆盖父配置
- `from` 键本身不参与合并
- 父配置自身可再含 `from`，会递归解析

#### **示例**

```toml
# 单个配置源（简写形式）
[from]
url = "file://./base.toml"
format = "toml"
```

```toml
# 多个配置源（列表形式）
[[from]]
url = "file://./base.toml"
format = "toml"
[[from]]
url = "https://example.com/shared-config.toml"
format = "yaml"
```

```toml
# 以 .mrpack 整合包作为父配置（提取其模组清单）
[from]
url = "https://example.com/packs/base.mrpack"
format = "mrpack"
```

---

### 2. `metadata` —— 整合包元数据管理

这部分主要用于描述 `.mrpack` 整合包的元信息，在资源分发或展示时非常有用。

#### **字段说明**

- `name`：整合包名称（默认 `"ModFetch Pack"`）
- `version`：包版本号（字符串，默认 `"1.0.0"`）
- `description`：简要描述该整合包内容

#### **示例**
```toml
[metadata]
name = "光影优化整合包"
version = "1.2"
description = "包含高性能和高质量光影模组的 Minecraft 整合方案"
```

---

### 3. `minecraft` —— 游戏客户端核心配置

定义 Minecraft 版本、模组加载器以及所要下载的模组、资源包等。

#### **主要字段**

- `version`（**必填**）：Minecraft 版本，支持数组（如 `["1.21.1", "1.20.4"]`）
- `mod_loader`：模组加载器，支持 `fabric`、`forge`、`neoforge`、`quilt`（默认 `fabric`）
- `mods`、`resourcepacks`、`shaderpacks`：分别表示模组、资源包、光影包的列表
  - 四类条目（含 `extra_urls`）至少配置其一，否则校验失败
- 每条目支持两种写法：
  - **简洁写法（仅 ID 或 slug 字符串）**
  - **详细写法（包含额外配置的字典结构）**

详细字段说明（`mods` / `resourcepacks` / `shaderpacks` 通用）：

| 字段           | 类型                    | 描述                                                  |
| -------------- | ----------------------- | ----------------------------------------------------- |
| `id`, `slug`   | string                  | 模组唯一标识，优先使用 Modrinth 的项目 ID 或 slug           |
| `version`      | string（可选）          | 固定版本号（默认取该 MC 版本×加载器下的最新版本）           |
| `only_version` | Array<String> 或 string （可选）| 当 Minecraft 版本匹配时才下载      |
| `feature`      | Array<String> 或 string （可选） | 运行时特征标记（启用条件，见下）            |

> **条件编译语义（`only_version` 与 `feature`）**
> - `only_version`：条目仅在声明的 Minecraft 版本下生效；列表时命中其一即可
> - `feature`：条目仅在**所有**声明的 feature 都被启用时才生效（AND 语义）；
>   未声明 `feature` 的条目始终包含
> - 二者组合时需**同时满足**（AND）
> - 判定方式：CLI 的 `-f/--feature` 或配置顶层 `features` 提供启用列表；
>   构建计划（`plan_build`）与本地校验共用同一过滤逻辑，保证行为一致
> - 注意：历史版本曾存在过滤失效/反向语义缺陷，现统一为"启用条件"语义

#### **高级字段：`extra_urls`（额外文件）**

允许用户定义一些非 Modrinth 来源的额外文件（会注入构建计划并打包进
`.mrpack` 的 `overrides/` 目录），配置字段如下：

| 字段           | 类型           | 描述                                                      |
| -------------- | -------------- | --------------------------------------------------------- |
| `url`          | string         | 文件的下载地址（支持 `file://` 本地文件）                 |
| `filename`     | string（可选） | 设置目标文件名（默认为从 URL 提取的文件名）               |
| `type`         | string         | 指定文件类型：`mod`, `resourcepack`, `shaderpack`, `file` |
| `sha1`         | string（可选） | SHA1 校验，防止文件重复或损坏                             |
| `only_version` | string 或 Array<String>（可选） | 指定版本触发下载的条件             |
| `feature`      | string 或 Array<String>（可选） | 运行时特征筛选                      |

> **目的地约定**：`type = "file"` 的文件放入整合包根目录（`overrides/` 根）；
> `mod`/`resourcepack`/`shaderpack` 类型分别进入 `overrides/mods/`、
> `overrides/resourcepacks/`、`overrides/shaderpacks/` 等对应子目录。

#### ⚠️ 光影加载器约束（shaderpacks）

配置声明了 `shaderpacks`（光影包）时，`mods` 中**必须包含光影加载器之一**：
`iris`、`oculus`、`optifine`（`oculus` 与 `iris` 等价——它是 iris 的
Forge/NeoForge 移植版）。

- 该约束在**本地校验阶段**即检查（不依赖网络）：若某 Minecraft 版本下
  存在实际生效（未被 `only_version`/`feature` 过滤掉）的光影包，但
  `mods` 中没有对应生效的光影加载器，则以错误码 `E102` 提前终止，不会
  静默跳过
- 光影包在 Modrinth 解析时**以实际配置的光影加载器作为 loader 过滤**，
  匹配光影包版本声明的兼容加载器；未配置加载器时不过滤 loader

示例：
```toml
[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = [
    "sodium",
    "iris",                    # ← 光影加载器，为下方光影包提供支持
]
shaderpacks = ["complementary-reimagined"]
```

#### **示例**

```toml
[minecraft]
version = ["1.21.1", "1.21.7"]
mod_loader = ["fabric", "forge"]   # 多加载器 → 每版本 × 每加载器各构建一次

mods = [
    # 用 dict 形式指定详细参数
    { id = "sodium", only_version = "1.21.7", feature = "performance" },
    { id = "lithium", feature = ["performance"] },
    { id = "iris", feature = "shaders" },
    # 简写形式（默认适用于所有版本、所有已启用 feature）
    "modmenu",
    "rei"
]

resourcepacks = [
    { id = "faithful", only_version = ["1.21.1", "1.20.4"] },
    { id = "fast-better-grass", feature = "shader-speed" }
]

shaderpacks = [
    { id = "complementary-reimagined", feature = "shaders" }
]

extra_urls = [
    { url = "https://example.com/cfg/my_shader.cfg", type = "file", filename = "shader_config.txt", only_version = "1.21.1" },
    { url = "file://./local_mods/coolmod.jar", type = "mod" }
]
```

---

### 4. `output` —— 输出配置

控制 ModFetch 下载后的内容输出方式。

#### **字段说明**

- `download_dir`：最终文件的存储目录（默认 `"downloads"`）
- `format`：输出格式，支持 `zip` 和 `mrpack`（默认 `["zip"]`），可指定多个（如 `["zip", "mrpack"]`）
- `mrpack_modes`：指定生成 `.mrpack` 的模式（数组，默认 `["download"]`），支持：
    - `download`：下载所有模组到整合包内（`overrides/` 目录）
    - `reference`：不下载平台模组，仅在 `modrinth.index.json` 中引用（轻量整合包）
      - 该模式下 `overrides/` 仅包含 `extra_urls` 来源的自定义文件
    - 两种模式下 `modrinth.index.json` 的 `files` 均会填充平台模组引用清单
      （`download` 的模组同时物理存在于 `overrides/`）

#### **示例**
```toml
[output]
download_dir = "./modpacks"
format = ["mrpack"]
# 同时生成“全量下载版”和“引用版”整合包
mrpack_modes = ["download", "reference"]
```

---

### 5. `plugins` —— 插件配置

声明要启用的插件（内置插件或已注册模块名），并可为各插件提供配置。

#### **字段说明**

- `enabled`：要启用的插件名列表（如 `"progress"`、`"notify"`）
- `configs`：按插件名索引的可选配置字典

#### **示例**
```toml
[plugins]
enabled = ["progress", "notify"]

[plugins.config.notify]
webhook_url = "https://example.com/webhook"
```

---

## 💡 完整的配置示例

```toml
# 全局重试与并发配置（根表键，必须放在所有 [table] 之前）
max_concurrent = 10
max_retries = 5
retry_delay = 2.0
verify_ssl = true
features = ["performance", "texture"]

[from]
url = "file://./base_config.toml"
format = "toml"

[metadata]
name = "高性能MC整合包"
version = "1.2.1"
description = "轻量化且优化良好的 Minecraft 模组整合方案"

[minecraft]
version = ["1.21.7", "1.21.1"]
mod_loader = ["fabric", "forge"]

mods = [
    { id = "sodium", only_version = "1.21.7", feature = "performance" },
    { id = "lithium", feature = "performance" },
    { id = "modmenu", feature = "utility" },
    { id = "fabric-api", sha1 = "a1b2c3d4e5f6ac231e45f787ac03fcd6be975b33" },
    "rei"
]

resourcepacks = [
    { id = "faithful", only_version = "1.21.7", feature = "texture" }
]

shaderpacks = [
    { id = "complementary-reimagined", feature = "shaders" }
]

extra_urls = [
    { url = "https://example.com/cfg/mod_config.cfg", type = "file", filename = "mod_settings.cfg", only_version = "1.21.7" }
]

[output]
download_dir = "./downloads"
format = ["zip", "mrpack"]
mrpack_modes = ["download", "reference"]

[plugins]
enabled = ["progress"]
```

---

## 🖥️ CLI 用法

```bash
modfetch [OPTIONS] COMMAND [ARGS]...

命令:
  build    执行完整构建（下载 + 打包）
  plan     仅生成构建计划（不下载/打包）
  check    校验配置（不下载、不打包）
  plugins  列出已加载的插件
  clean    清理构建工作区 / 全局缓存

通用选项:
  -c, --config TEXT    配置文件路径（默认: 当前目录 mods.toml）
  -f, --feature TEXT   启用的功能标签（可多次；未传时保留配置顶层 features 默认值）
  --plugin TEXT        加载插件（可多次；.lua 走 Lua loader，其余走 Python loader）
  --plugin-dir TEXT    插件目录路径（递归扫描其中的 .py 与 .lua 文件）
  --debug              启用调试模式（DEBUG 日志）
  --version            显示版本
  --help               显示帮助
```

示例：

```bash
modfetch build                  # 使用当前目录 mods.toml 构建
modfetch build -c other.toml    # 指定其他配置文件
modfetch check -c mods.toml     # 只校验配置，不下载/打包
modfetch plan -o plan.json      # 生成构建计划到文件（默认输出到 stdout）
modfetch clean --cache          # 清理构建工作区 + 全局缓存
modfetch plugins --plugin-dir ./plugins   # 查看指定目录下加载了哪些插件
```

> 注意：`-f/--feature` 与配置顶层 `features` 共同决定条件编译结果；
> 显式传入 `-f` 时会覆盖配置顶层 `features` 作为校验/构建的启用集合；
> 未传 `-f` 时保留配置顶层 `features` 默认值（如 `features = ["performance"]`）。

---

## 💡 使用建议

- 仅可使用 `Modrinth` 的项目 ID 或 slug。
- 如果配置复杂，建议分开 `[from]` 文件用于模块化管理。
- `only_version` 和 `feature` 字段非常适合用于根据不同场景（如性能、美观、教育）组织模组依赖。
- 配置了光影包时记得在 `mods` 中放入对应的光影加载器（`iris` / `oculus` / `optifine`），否则本地校验会拒绝该配置。
- 需要分发"轻量"整合包时，使用 `mrpack_modes = ["reference"]`；需要开箱即用时用 `["download"]`。
