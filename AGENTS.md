# PROJECT KNOWLEDGE BASE

**Generated:** 2026-02-20
**Commit:** 26b39a4
**Branch:** master

## OVERVIEW
Minecraft mod downloader with Python CLI + Vue 3 UI. Fetches mods from Modrinth API, resolves dependencies, builds modpacks.

## STRUCTURE
```
./
├── modfetch/           # Python backend (CLI + core)
│   ├── api/           # Modrinth API wrapper
│   ├── download/      # File download
│   ├── models/        # Data models
│   ├── services/      # Resolvers (dep, mod, version)
│   ├── packager/      # Modpack creation
│   └── plugins/       # Plugin system (empty)
├── modfetch-ui/       # Vue 3 frontend
│   └── src/           # Element Plus + VueUse
├── .github/workflows/ # CI (build.yml, pypi.yml)
└── build.py           # Nuitka build script
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| CLI commands | `modfetch/cli.py` |
| API client | `modfetch/services/api_client.py` |
| Dependency resolution | `modfetch/services/dependency_resolver.py` |
| Download logic | `modfetch/download/` |
| Frontend | `modfetch-ui/src/App.vue` |

## COMMANDS
```bash
# Python
uv sync --dev          # Install deps
uv run modfetch        # Run CLI

# Frontend (cd modfetch-ui)
pnpm install           # Install deps
pnpm dev               # Dev server
pnpm build             # Build

# Build standalone
python build.py        # Nuitka → executables
```

## CONVENTIONS
- Python: `loguru` for logging, `aiohttp` for async HTTP
- Frontend: Vue 3 Composition API + Element Plus
- Build: Nuitka compiles Python → single binary
- Entry: `modfetch/__main__.py` → `modfetch/__main__:cli_main`

## ANTI-PATTERNS (THIS PROJECT)
- No ruff/lint config found - project relies on defaults
- No type annotations visible in some modules

## NOTES
- Downloads stored in `./downloads/`
- `mods.toml` - mod metadata config
- Dual platform build (Linux + Windows via CI)
