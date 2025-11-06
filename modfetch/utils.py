from typing import Optional
from modfetch.api.base import ModLoader
import aiohttp
import toml

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


async def get_loader_version(loader: ModLoader, mc_version: str) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        if loader == ModLoader.FORGE or loader == ModLoader.NEOFORGE:
            if loader == ModLoader.FORGE:
                url = f"https://bmclapi2.bangbang93.com/forge/minecraft/{mc_version}"
            else:
                url = f"https://bmclapi2.bangbang93.com/neoforge/list/{mc_version}"
            async with session.get(
                f"https://bmclapi2.bangbang93.com/forge/minecraft/{mc_version}",
            ) as response:
                if response.status != 200:
                    return None
                versions = await response.json()
                if versions:
                    return versions[-1]["version"]
        elif loader == ModLoader.FABRIC or loader == ModLoader.QUILT:
            if loader == ModLoader.FABRIC:
                url = f"https://bmclapi2.bangbang93.com/fabric-meta/v2/versions/loader/{mc_version}"
            else:
                url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}"
            async with session.get(
                url,
            ) as response:
                if response.status != 200:
                    return None
                versions = await response.json()
                if versions:
                    return versions[0]["loader"]["version"]
    return None


async def get_config(url: str, format: str) -> Optional[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            if format == "json":
                return await response.json()
            elif format == "toml":
                return toml.loads(await response.text())
            elif format == "yaml":
                if not HAS_YAML:
                    return None
                else:
                    return yaml.safe_load(await response.text())  # type: ignore
