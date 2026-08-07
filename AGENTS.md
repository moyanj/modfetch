# PROJECT KNOWLEDGE BASE

**Updated:** 2026-08-07
**Branch:** refactor/hexagonal-architecture

## OVERVIEW
Minecraft 模组下载/打包工具：Python 后端（modfetch/）+ Vue 3 前端（web/，独立 pnpm 工程）+ GitHub Actions CI。
从 Modrinth API 拉取模组、解析依赖、构建整合包，支持多 Minecraft 版本 × 多加载器一次构建。

后端架构：hexagonal（domain → ports → application → adapters）。CLI 与 Web 是薄适配层，统一走 `BuildApplicationService`。

## STRUCTURE
```
./
├── modfetch/         # Python 后端包（六边形架构）
│   ├── domain/       # 纯模型，零基础设施依赖（AST 检查约束）
│   ├── ports/        # Protocol 接口（catalog/downloader/packager/event_sink…）
│   ├── application/  # 用例：build_service/plan_build/execute_build/config_service
│   ├── adapters/     # 端口实现 → 详见 modfetch/AGENTS.md
│   ├── plugins/      # Python/Lua 插件系统 → 详见 modfetch/plugins/AGENTS.md
│   ├── server/       # FastAPI 薄适配层（routes/ws/schemas/app）
│   ├── composition.py# DI 组装根（create_build_service）
│   ├── cli.py        # CLI 适配层
│   ├── logger.py     # loguru 配置（包根横切关注点）
│   └── __main__.py   # 入口代理 → cli.main
├── web/              # Vue 3 + TS + Vite 前端（pnpm）→ 详见 web/AGENTS.md
├── tests/            # unit/integration/contract + fixtures（离线）
├── examples/         # 插件示例（Python + Lua）
├── .github/workflows/# build.yml（CI）/ release.yml（发布）
├── logo/             # Nuitka 图标素材（.ico + .png）
├── nuitka_build.py   # Nuitka 构建脚本（产出 modfetch.bin）
├── mods.toml         # 示例用户配置
└── pyproject.toml    # 依赖/入口/pytest 配置
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| Build orchestration | `modfetch/application/build_service.py` |
| Config parse/validate | `modfetch/application/config_service.py` + `validation.py` |
| Plan generation (expand×resolve) | `modfetch/application/plan_build.py` |
| Dependency graph | `modfetch/application/dependency_resolver.py` |
| Mod resolver / version matching | `modfetch/application/mod_resolver.py` / `version_matcher.py` |
| Modrinth HTTP | `modfetch/adapters/modrinth/client.py` |
| Download execution | `modfetch/adapters/download/executor.py` + `http_downloader.py` |
| Packaging | `modfetch/adapters/packaging/` |
| Web job management | `modfetch/adapters/jobs/` |
| Event protocol | `modfetch/domain/events.py` |
| Errors (hierarchy) | `modfetch/domain/errors.py` |
| DI wiring | `modfetch/composition.py` |
| CLI entry | `modfetch/cli.py` (`main`) |
| Server entry | `modfetch/server/app.py` (`create_app`) / `server/__main__.py` |
| Frontend | `web/` |

## COMMANDS
```bash
uv sync --dev            # 安装依赖（dev 组：nuitka/pytest/pytest-asyncio）
uv run modfetch          # 运行 CLI（⚠️ 见 ANTI-PATTERNS：入口声明需修复）
uv run pytest            # 测试（pytest-asyncio auto 模式）
uv run nuitka_build.py   # Nuitka → modfetch.bin（CI 同款；不是 python build.py）
```

## CONVENTIONS
- Python >=3.10（无 .python-version）；`uv` 管理依赖，`uv.lock` 被 gitignore（不提交锁文件）
- `domain/` 必须保持零 aiohttp/fastapi/click/loguru 导入（hexagonal 依赖方向）
- 错误以值传递（`DownloadResult`/`BuildResult.errors`），**禁止静默吞没**（`except: pass`）
- Logging via `loguru`；async via `aiohttp`/`aiofiles`（仅 adapters）
- 测试必须完全离线：`mock_modrinth` fixture / 内存 `stub_catalog`，禁止真实网络
- 错误消息使用中文（`必须提供…` 句式）；`type: ignore` 尽量带错误码与原因
- 生产构建走 Nuitka（onefile），双平台 CI（ubuntu + windows，Python 3.10）

## Anti-Patterns (THIS PROJECT)
- 旧导入路径（`modfetch.models` / `modfetch.exceptions` / `modfetch.services` / `modfetch.download` / `modfetch.packager`）**已删除**，迁移到 `domain`/`application`/`adapters`（见 commit `8e43962` 迁移表）
- 静默吞没错误（空 except / 不返回结构化结果）
- 在 domain 层引入基础设施 import
- 裸 `# type: ignore`（无错误码）
- `python build.py`（不存在）——构建脚本是 `nuitka_build.py`

## KNOWN GOTCHAS (待修复)
- **`pyproject.toml` 入口声明损坏**：`modfetch = "modfetch.__main__:cli_main"`，但代码只有 `cli.main`（无 `cli_main`）。`uv run modfetch` 会 ImportError
- CLI `--version` 硬编码 `0.1.0`，与 `__version__`/pyproject `0.2.0` 不一致
- `server/app.py` 静态挂载路径 `modfetch/server/app.py` 的 `parent.parent` = `modfetch/`，实际 `web/` 在项目根，路径应为 `parent.parent.parent`
- `server/app.py` 用弃用的 `@app.on_event`；CORS `allow_origins=["*"]` + `allow_credentials=True` 是非法组合
- **CI `build.yml` 名为 "Build and Test" 但不跑测试**（仅构建）
- `web/` 前端未纳入 CI（无 Node/pnpm 步骤）
- 领域纯净性 "AST-checked" 目前无落地检查文件；`_validate_plugin_source`（plugins/loader.py）是唯一 AST 检查
- `ValidationError`（E500）与 `APIServerError`（HTTP 5xx）错误码冲突

## NOTES
- 构建产物 / 下载走 `./downloads/`（gitignored）；Nuitka 产出各平台 `modfetch.bin`
- `post.py` 是根级独立插件（非包代码，经 `--plugin ./post.py` 加载）
- `uv.lock` 不提交 → CI 每次 `uv sync` 重新解析，构建非确定性（待评估是否纳入版本控制）
- 文档入口：`docs.md`（配置格式规范，含条件编译/光影加载器约束）与 `README.md`（用户指南）
- 配置格式实际支持 toml/yaml/json（`ParentConfig.format` 校验仍列出 xml，但解析器未实现，文档按实际能力编写）