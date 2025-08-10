from calendar import c
from modfetch.core import ModFetch
import toml
import asyncio
import click


async def main(config_path: str):
    modfetch = ModFetch(toml.load(config_path))
    await modfetch.start()


@click.command()
@click.option("-c", "--config", default="mods.toml", help="Path to config file")
def cli_main(config):
    asyncio.run(main(config))


if __name__ == "__main__":
    cli_main()
