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
├── adapters/       # modrinth/ download/ packaging/ events/ config/ jobs/
├── services/       # Legacy resolvers (ModResolver/VersionMatcher/MrpackResolver)
├── plugins/        # Plugin hooks (Python/Lua)
├── server/         # FastAPI thin adapter (routes/ws/schemas)
├── models/         # COMPAT SHIM → domain
├── download/       # COMPAT SHIM → adapters/download
├── exceptions.py   # COMPAT SHIM → domain.errors
├── composition.py  # DI composition root (create_build_service)
└── cli.py          # CLI adapter
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| Build orchestration | `application/build_service.py` |
| Plan generation | `application/plan_build.py` |
| Config boundary | `application/config_service.py` |
| Modrinth HTTP | `adapters/modrinth/client.py` |
| Download execution | `adapters/download/executor.py` |
| DI wiring | `composition.py` |

## CONVENTIONS
- Async throughout (`aiohttp`, `aiofiles`) — in adapters only
- Logging via `loguru`
- Errors flow as values (`DownloadResult`/`BuildResult.errors`), never swallowed
- `domain/` purity enforced by AST check (no infra imports)
- Entry: `modfetch/__main__:cli_main`

## ANTI-PATTERNS
- No ruff linting configured
- Compat shims (`modfetch.models` etc.) are deprecated — import from
  `modfetch.domain` / `modfetch.adapters` in new code
