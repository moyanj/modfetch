from modfetch.core import ModFetch
import toml
import asyncio


async def main():
    modfetch = ModFetch(toml.load("mods.toml"))
    await modfetch.start()


asyncio.run(main())
