"""向后兼容 shim — ModrinthClient 已迁入 modfetch.adapters.modrinth"""

from modfetch.adapters.modrinth.client import (  # noqa: F401
    MODRINTH_BASE_URL,
    ModrinthClient,
)

__all__ = ["ModrinthClient", "MODRINTH_BASE_URL"]
