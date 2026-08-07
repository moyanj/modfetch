# PROJECT KNOWLEDGE BASE

**Updated:** 2026-08-07
**Branch:** refactor/hexagonal-architecture

## OVERVIEW
Minecraft mod downloader with Python CLI + FastAPI server. Fetches mods from Modrinth API, resolves dependencies, builds modpacks. Supports building for multiple Minecraft versions and mod loaders simultaneously.

Architecture: hexagonal (domain → ports → application → adapters). CLI and Web are thin adapters over a shared `BuildApplicationService`.

## STRUCTURE
```
./
├── modfetch/
│   ├── domain/        # Pure domain models, ZERO infrastructure deps
│   ├── ports/         # Dependency interfaces (Protocol)
│   ├── application/   # Use-case orchestration (BuildApplicationService)
│   ├── adapters/      # Port implementations
│   │   ├── modrinth/  # Modrinth API (CatalogPort)
│   │   ├── download/  # HttpDownloader/FileStore/Executor/RetryPolicy
│   │   ├── packaging/ # Mrpack/Zip packagers + dispatcher
│   │   ├── events/    # EventSinks (null/log/job/composite)
│   │   ├── config/    # TOML/YAML/JSON sources + inheritance
│   │   └── jobs/      # Web job management (in-memory)
│   ├── plugins/       # Plugin system (Python/Lua)
│   ├── server/        # Web adapter (thin FastAPI routes)
│   ├── services/      # Legacy resolvers (used by application layer)
│   ├── models/        # COMPAT SHIM → domain
│   ├── download/      # COMPAT SHIM → adapters/download
│   ├── exceptions.py  # COMPAT SHIM → domain.errors
│   ├── composition.py # DI composition root
│   └── cli.py         # CLI adapter
├── tests/             # unit/ integration/ contract/
└── build.py           # Nuitka build script
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| Build orchestration | `modfetch/application/build_service.py` |
| Config parse/validate | `modfetch/application/config_service.py` |
| Plan generation (expand×resolve) | `modfetch/application/plan_build.py` |
| Dependency graph | `modfetch/application/dependency_resolver.py` |
| Modrinth HTTP | `modfetch/adapters/modrinth/client.py` |
| Download execution | `modfetch/adapters/download/executor.py` |
| Packaging | `modfetch/adapters/packaging/` |
| Event protocol | `modfetch/domain/events.py` |
| DI wiring | `modfetch/composition.py` |

## COMMANDS
```bash
uv sync --dev          # Install deps
uv run modfetch        # Run CLI
uv run pytest          # Run test suite
python build.py        # Nuitka → executables
```

## CONVENTIONS
- Python: `loguru` for logging, `aiohttp` for async HTTP (adapters only)
- `domain/` must stay free of aiohttp/fastapi/click/loguru imports (AST-checked)
- Errors flow as values (`DownloadResult`/`BuildResult.errors`), never swallowed
- Backward-compat shims re-export from new locations; deprecated
- Entry: `modfetch/__main__.py` → `modfetch/__main__:cli_main`

## NOTES
- Downloads stored in `./downloads/`
- `mods.toml` - mod metadata config
- Dual platform build (Linux + Windows via CI)
