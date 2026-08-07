# MODFETCH (Python Backend)

Core Python package for Minecraft mod downloading and modpack creation.

Hexagonal architecture: `domain` (pure models) ← `ports` (Protocols) ←
`application` (use cases) ← `adapters` (implementations). CLI and FastAPI
server are thin adapters over `BuildApplicationService`.

## STRUCTURE
```
modfetch/
├── domain/         # Pure domain models (NO aiohttp/fastapi/click/loguru)
├── ports/          # Dependency interfaces (Protocol)
├── application/    # Use cases: build_service / plan_build / execute_build
│                   #   + mod_resolver / version_matcher / dependency_resolver
├── adapters/       # modrinth/ download/ packaging/ events/ config/ jobs/
├── plugins/        # Plugin hooks (Python/Lua)  → 见 plugins/AGENTS.md
├── server/         # FastAPI thin adapter (routes/ws/schemas)
├── composition.py  # DI composition root (create_build_service)
├── cli.py          # CLI adapter (click; 注意入口是 main 非 cli_main)
├── logger.py       # loguru 配置（包根横切关注点）
└── __main__.py     # 入口代理 → cli.main
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| Build orchestration | `application/build_service.py` |
| Plan generation | `application/plan_build.py` |
| Config boundary | `application/config_service.py` + `validation.py` |
| Dependency graph | `application/dependency_resolver.py` |
| Mod resolver / version match | `application/mod_resolver.py` / `version_matcher.py` |
| Modrinth HTTP | `adapters/modrinth/client.py` |
| Download execution | `adapters/download/executor.py` + `http_downloader.py` |
| Packaging | `adapters/packaging/` |
| Web job management | `adapters/jobs/` |
| Event protocol | `domain/events.py` |
| Errors (hierarchy) | `domain/errors.py` |
| DI wiring | `composition.py` |
| CLI entry | `cli.py` (`main`) |
| Server entry | `server/app.py` (`create_app`) / `server/__main__.py` |

## CONVENTIONS
- Async throughout (`aiohttp`, `aiofiles`) — in adapters only
- Logging via `loguru`
- Errors flow as values (`DownloadResult`/`BuildResult.errors`), never swallowed
- `domain/` purity enforced by AST check (no infra imports)
- Entry: `modfetch/__main__.py` → `modfetch.cli:main`（⚠️ pyproject 声明为 `cli_main`，待修复）
- 错误消息中文（`必须提供…`）；`type: ignore` 尽量带错误码

## ANTI-PATTERNS
- No ruff linting configured（质量靠审查）
- 静默吞没错误（空 except / 不返回结构化结果）
- 旧导入路径 `modfetch.models/exceptions/services/download/packager` 已删除 → 用 domain/application/adapters
- 裸 `# type: ignore`（无错误码）
- domain 层引入 aiohttp/fastapi/click/loguru
