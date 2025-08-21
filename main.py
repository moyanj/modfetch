import asyncio
import click
import toml
import json
import yaml
import aiofiles

from modfetch.core import ModFetch


async def main(config_path: str):
    if config_path.endswith(".toml"):
        cfg = toml.load(config_path)
    elif config_path.endswith(".json"):
        async with aiofiles.open(config_path) as cfg_file:
            cfg = json.loads(await cfg_file.read())
    elif config_path.endswith(".yaml"):
        async with aiofiles.open(config_path) as cfg_file:
            cfg = yaml.load(await cfg_file.read(), yaml.Loader)
    else:
        raise ValueError("Invalid config file format")
    modfetch = ModFetch(cfg)
    await modfetch.start()


@click.command()
@click.argument("config", type=click.Path(exists=True), default="mods.toml")
def cli_main(config):
    asyncio.run(main(config))


if __name__ == "__main__":
    cli_main()
