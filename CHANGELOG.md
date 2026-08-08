# Changelog

本项目的所有重要变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 待定

## [1.0.1] - 2026-08-08

### 🐛 修复

- **file:// 资源未校验 SHA1**：本地文件复制后按 `expected_sha1` 校验，
  防止篡改/损坏的本地源文件被当作完整制品缓存复用；校验失败清理残留并报 `E302`。
- **物化失败后仍打包**：硬链接/复制失败时跳过该 target 的打包，
  不再产出缺少模组的残缺 ZIP/mrpack；工作区缺文件时 `outputs` 为空且 `dist` 无产物。
- **mrpack DOWNLOAD 模式 `manifest.files` 为空**：download 模式同样填充
  catalog 制品引用（便于第三方工具识别包内模组清单），`extra_urls` 文件仍只落 `overrides`。
- **加载器依赖 ID 修正**：forge/neoforge 的 mrpack 依赖 ID 不再错误拼成
  `forge-loader`/`neoforge-loader`，改用规范值 `forge`/`neoforge`。
- **Web 健康检查版本号残留**：`/api/health` 的版本号由残留的 `0.2.0`
  改为引用包级 `__version__`，消除硬编码重复。

### 📦 版本

- 后端 / 前端 / API 元数据统一升级至 `1.0.1`。

## [1.0.0] - 2026-08-08

### 🎉 超级重大更新：架构全面重写

这是 ModFetch 从实验性工具走向正式版的关键一跃。本次更新对代码库进行了
**彻底的重构**：从早期的单体实现迁移到清晰的**六边形架构**
（`domain` → `ports` → `application` → `adapters`），
同时引入了全新的构建流水线、缓存体系和命令行体验。

> ⚠️ **破坏性变更**：本版本为 1.0.0 正式版，CLI 用法与 v0.2.0 不兼容，
> 详见下方「CLI 变更」与「迁移指南」。

> ℹ️ 说明：`extra_urls`、mrpack 的 download/reference 模式、配置继承（`from`）、
> `only_version`/`feature` 条件配置、Lua 插件运行时、光影包/资源包支持、
> Web 界面等能力在 v0.2.x 已存在，仅在本版本中完善与修正，不再重复列入「新特性」。

### 🧱 架构重构

- **六边形架构落地**：建立领域层（domain）、端口层（ports）、应用层（application）、
  适配层（adapters），删除旧 `models/exceptions/services/download/packager` 分层。
- **统一应用入口**：CLI 与 Web 共用 `BuildApplicationService`，构建/计划/校验同一编排；
  依赖解析无状态化（per-call 上下文），循环依赖给出结构化诊断。
- **适配层解耦**：下载拆为 `HttpDownloader` / `FileStore` / `Executor`；
  打包抽离 `PackagerPort`，返回结构化 `OutputArtifact`，失败不再静默。
- **Web 瘦身**：删除 FS 扫描与裸 `aiohttp`，`JobManager` 接入应用服务，
  统一事件协议，新增 `JobEventSink` 事件翻译器。
- **彻底清理**：删除旧 Orchestrator 与死代码（保留向后兼容 shim）。

### ✨ 新特性

- **全新构建布局（三层）**：`build/cache`（内容寻址全局缓存）+ `build/{mc}-{loader}`
  （打包工作区）+ `dist/`（唯一扁平交付目录），配合**硬链接物化**（默认）
  或显式复制（`--link-mode copy`），重复构建几乎零下载、零冗余磁盘占用。
- **构建计划（Build Plan）**：引入独立计划用例与序列化能力，
  `modfetch plan` 先行生成完整计划（依赖图、解析结果、产物清单）输出到文件或 stdout。
- **光影包按加载器过滤**：版本查询以该版本生效的光影加载器（`iris`/`oculus`/`optifine`）
  作 loader 过滤，并新增跨字段关联校验——配置了实际生效的光影包时，
  `mods` 必须包含对应光影加载器，错误在构建前即可发现。
- **条件过滤贯通远程校验**：`only_version`/`feature` 条件此前仅在本地过滤，
  本版本让远程校验按版本粒度先行条件过滤再查兼容性，消除误报 `INCOMPATIBLE`。
- **异构 `mods` 数组**：配置解析切换至标准库 `tomllib`/`tomli`，
  同数组内可混用 slug 字符串与结构化对象（旧 `toml` 库要求同构数组，无法解析）。
- **CLI 接入 Lua 插件**：插件目录与显式插件路径按 `.lua`/`.py` 分发到对应加载器，
  接入 `LuaPluginLoader` 完整生命周期（initialize/shutdown）。
- **REFERENCE 模式下处理 `extra_urls` 文件**：引用型整合包也能正确携带额外文件清单与内容。
- **下载至指定目录并保持子目录结构**：额外文件的子目录路径在打包时得以保留。
- **新增 `verify_ssl` 配置项**（默认 `True`）并透传至构建服务，可关闭 TLS 校验。

### 🖥️ CLI 变更（破坏性）

- 由单命令 + 多个 flag 重构为 **子命令风格**：
  `build` / `plan` / `check` / `plugins` / `clean`。

| 旧用法（v0.2.x） | 新用法（v1.0.0） |
|---|---|
| `modfetch mods.toml` | `modfetch build`（默认 `mods.toml`，`-c` 覆盖） |
| `modfetch --dry-run mods.toml` | `modfetch check` |
| `modfetch --plan --plan-out f.json mods.toml` | `modfetch plan -o f.json` |
| `modfetch --clean-cache mods.toml` | `modfetch clean --cache` |
| `modfetch --clean-build mods.toml` | `modfetch clean` |
| `modfetch --list-plugins mods.toml` | `modfetch plugins` |

### 🚀 性能与稳定性

- **消除请求放大**：修复发往 Modrinth 的重复/冗余请求，减少接口放大与事件循环阻塞。
- 并发下载统一并发控制，错误以结构化结果传递。
- **修复 `aiohttp` 会话泄漏**：调用链显式释放（close），长任务稳定运行。
- **全链路日志打点**：下载/解析/物化/打包关键阶段日志补齐。

### 🐛 修复

- **下载失败跳过物化**：不再半途中断或产生脏文件。
- **`feature` 默认值语义**：未传 `-f` 时保留配置顶层 `features` 默认值，不被空列表覆盖。
- **条件剔除反向过滤 bug**：修复 feature 全部启用时条件对应条目被误排除的问题。
- 修正示例配置的合法性。

### 📚 文档与示例

- **全新 README**：功能导向重写，含同类工具对比与选用建议。
- **六类配置示例**（`examples/`）：最小可用、多 target、配置继承、条件编译、资源包/光影、插件。

### 迁移指南（v0.2.x → v1.0.0）

1. **命令行**：按上方「CLI 变更」表调整命令；
2. **配置文件**：`mods` 数组中混用 slug 与结构化对象不再受限（解析器升级，无需改动即可获益）；
3. **构建布局**：构建目录已更新为 `build/cache + build/{mc}-{loader} + dist` 三层结构，
   旧版产出目录需手动清理；
4. **`verify_ssl`**：默认 `True`，如需关闭请在配置中显式设置。

## [0.2.0] - 2026-07-08

### 新特性

- **支持从 `.mrpack` 文件继承配置**（`from`）：新增 mrpack 配置解析服务，
  扩展此前仅支持本地/远程 URL 的配置继承能力。
- **`.mrpack` 模式配置**：新增 `mrpack_modes`（`download` / `reference`）选项。
- **Lua 插件运行时与加载器**：新增 Lua 插件示例与文档。
- **固定模组版本**：支持 `slug/id@version` 语法锁定模组具体版本。
- **多加载器 / 多版本同时构建**：一份配置矩阵式展开多个目标。
- **Web 服务器与前端**：FastAPI + WebSocket 服务器，前端轮询与 WebSocket 实时同步任务状态；
  远端配置验证与模组自动补全；暗色模式支持。
- **Nuitka 构建参数**：可执行文件输出适配 Windows 平台。

### 其他

- 新增 LICENSE（MIT）；重构 API 客户端；插件化下载/API 提供商。
- 改进 Nuitka 构建工作流与依赖管理。

## [0.1.1] - 2025-08-22

首个打 tag 的版本（此前为未打 tag 的初始开发）。

### 初始特性

- **CLI 入口**：`modfetch <config>` 命令行接口，支持 `--feature` 特性参数。
- **配置加载**：多配置源（本地文件 / 远程 URL），支持配置继承（`from`）；
  支持 `mods.toml`（数组配置模组列表）、XML、YAML/JSON 格式。
- **下载处理**：并发下载、`extra_urls` 额外 URL、本地文件复制、
  资源包与光影包支持（含目录结构处理）、错误处理与 `safe_print` 输出。
- **打包**：MrPack 整合包生成流程与文件结构优化。
- **项目整理**：重构配置处理并分离 Minecraft 相关设置；删除冗余代码；创建 README。

### 修复

- 重构 API 客户端并调整 Python 版本要求。