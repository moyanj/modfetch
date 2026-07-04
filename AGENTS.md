# PROJECT KNOWLEDGE BASE

**Generated:** 2026-02-20
**Commit:** 26b39a4
**Branch:** master

## OVERVIEW
Minecraft mod downloader with Python CLI. Fetches mods from Modrinth API, resolves dependencies, builds modpacks. Supports building for multiple Minecraft versions and mod loaders simultaneously.

## STRUCTURE
```
./
├── modfetch/           # Python backend (CLI + core)
│   ├── api/           # Modrinth API wrapper
│   ├── download/      # File download
│   ├── models/        # Data models (Supports multi-loader/multi-version)
│   ├── services/      # Resolvers (dep, mod, version)
│   ├── packager/      # Modpack creation
│   └── plugins/       # Plugin system (empty)
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

## COMMANDS
```bash
# Python
uv sync --dev          # Install deps
uv run modfetch        # Run CLI
# Build standalone
python build.py        # Nuitka → executables
```

## CONVENTIONS
- Python: `loguru` for logging, `aiohttp` for async HTTP
- Build: Nuitka compiles Python → single binary
- Entry: `modfetch/__main__.py` → `modfetch/__main__:cli_main`

## ANTI-PATTERNS (THIS PROJECT)
- No ruff/lint config found - project relies on defaults
- No type annotations visible in some modules

## NOTES
- Downloads stored in `./downloads/`
- `mods.toml` - mod metadata config
- Dual platform build (Linux + Windows via CI)
