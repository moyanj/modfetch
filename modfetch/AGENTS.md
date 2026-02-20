# MODFETCH (Python Backend)

Core Python package for Minecraft mod downloading and modpack creation.

## STRUCTURE
```
modfetch/
├── cli.py          # Click CLI entry
├── orchestrator.py # Main orchestration logic
├── api/            # Modrinth API wrappers
├── download/       # Async file download
├── models/         # Pydantic data models
├── services/       # API client, resolvers
├── packager/       # Modpack .zip creation
└── plugins/        # Plugin hooks (empty)
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| CLI args | `cli.py` |
| Download flow | `download/__init__.py` |
| API client | `services/api_client.py` |
| Resolver logic | `services/dependency_resolver.py` |

## CONVENTIONS
- Async throughout (`aiohttp`, `aiofiles`)
- Logging via `loguru`
- Exceptions in `exceptions.py`
- Entry: `modfetch/__main__:cli_main`

## ANTI-PATTERNS
- No type hints in some modules
- No ruff linting configured
