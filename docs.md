# **ModFetch 配置格式规范文档**

ModFetch 旨在提供灵活的配置支持，支持`toml`,`yaml`,`json`,`xml`。**默认推荐使用 `.toml` 格式，因其易于阅读和编写的特性。**

---

## 📚 总览

整个配置文件为一个嵌套结构的字典，可包含以下主要部分：

| **配置节**    | **描述**                                                     |
| ------------- | ------------------------------------------------------------ |
| `[from]`      | 用于指定远程或本地的父配置文件并继承其内容                   |
| `[metadata]`  | 包含整合包的元数据，用于 `.mrpack` 自描述格式                |
| `[minecraft]` | Minecraft 相关设置（版本、模组加载器、资源、模组等下载配置） |
| `[output]`    | 指定最终输出路径及后处理方式                                 |

---

## 🔧 配置字段详解

### 1. `from` —— 配置源继承

允许从本地路径或远程 URL 加载并继承其他配置文件。

#### **字段说明**

- `url`：配置文件的位置，支持 `file://`（本地路径）、`http(s)://`（远程地址）
- `format`：文件格式，默认为 `toml`，支持 `json`, `yaml`, `toml`，`xml`

#### **示例**
```toml
[from]
url = "file://./base.toml"
format = "toml"
```

---

### 2. `metadata` —— 整合包元数据管理

这部分主要用于描述 `.mrpack` 整合包的元信息，在资源分发或展示时非常有用。

#### **字段说明**

- `name`：整合包名称
- `version`：包版本号（字符串，例如 `"v1.2.0"`）
- `description`：简要描述该整合包内容
- `authors`：作者列表（字符串数组）

> 🔍 *建议保持简洁，并清晰描述整合包用途。*

#### **示例**
```toml
[metadata]
name = "光影优化整合包"
version = "1.2"
description = "包含高性能和高质量光影模组的 Minecraft 整合方案"
authors = ["John Doe", "Jane Smith"]
```

---

### 3. `minecraft` —— 游戏客户端核心配置

定义 Minecraft 版本、模组加载器以及所要下载的模组、资源包等。

#### **主要字段**

- `version`：Minecraft 版本，支持数组（如 `["1.21.1", "1.20.4"]`）
- `mod_loader`：模组加载器，支持 `fabric`, `forge`, `quilt`
- `mods`、`resourcepacks`、`shaderpacks`：分别表示模组、资源包、光影包的列表
    - 支持两种写法：
        - **简洁写法（仅ID或slug字符串）**
        - **详细写法（包含额外配置的字典结构）**

详细字段说明：

| 字段           | 类型                    | 描述                                                        |
| -------------- | ----------------------- | ----------------------------------------------------------- |
| `id`, `slug`   | string                  | 模组唯一标识，优先使用 Modrinth 的项目 ID 或 slug           |
| `only_version` | Array<String> 或 string （可选）| 当 Minecraft 版本匹配时才下载      |
| `feature`      | Array<String> 或 string （可选） | 用于运行时特征标记（如 performance、shader） |

#### **高级字段：`extra_files`（额外文件）**

允许用户定义一些非 Modrinth 来源的额外文件，配置字段如下：

| 字段           | 类型           | 描述                                                      |
| -------------- | -------------- | --------------------------------------------------------- |
| `url`          | string         | 文件的下载地址（支持 `file://` 本地文件）                 |
| `filename`     | string（可选） | 设置目标文件名（默认为原始文件名）                        |
| `type`         | string         | 指定文件类型：`mod`, `resourcepack`, `shaderpack`, `file` |
| `sha1`         | string（可选） | SHA1 校验，防止文件重复或损坏                             |
| `only_version` | Array<String> （可选） | 指定版本触发下载的条件                       |
| `feature`      | Array<String> （可选） | 运行时特征筛选                          |

#### **示例**
```toml
[minecraft]
version = ["1.21.1", "1.21.7"]
mod_loader = "fabric"

mods = [
    # 用 dict 形式指定详细参数
    { id = "sodium", only_version = "1.21.7", feature = "performance" },
    { id = "lithium", feature = ["performance"] },
    # 简写形式（默认适用于所有版本）
    "modmenu",
    "rei"
]

resourcepacks = [
    { id = "faithful", only_version = ["1.21.1", "1.20.4"] },
    { id = "fast-better-grass", feature = "shader-speed" }
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

- `download_dir`：最终文件的存储目录
- `format`：输出格式，支持 `zip` 和 `mrpack`，可指定多个（如 `["zip", "mrpack"]`）

#### **示例**
```toml
[output]
download_dir = "./modpacks"
format = ["mrpack"]
```

---

## 💡 完整的配置示例

```toml
[from]
url = "file://./base_config.toml"
format = "toml"

[metadata]
name = "高性能MC整合包"
version = "1.2.1"
description = "轻量化且优化良好的 Minecraft 模组整合方案"
authors = ["ModFetcher团队"]

[minecraft]
version = ["1.21.7"]
mod_loader = "fabric"

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

extra_urls = [
    { url = "https://example.com/cfg/mod_config.cfg", type = "file", filename = "mod_settings.cfg", only_version = "1.21.7" }
]

[output]
download_dir = "./downloads"
format = ["zip", "mrpack"]
```
