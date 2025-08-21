import asyncio
import click
import toml
import json
import yaml
import aiofiles
import xmltodict

from modfetch.core import ModFetch


async def main(config_path: str, feature: list[str]):
    if config_path.endswith(".toml"):
        cfg = toml.load(config_path)
    elif config_path.endswith(".json"):
        async with aiofiles.open(config_path) as cfg_file:
            cfg = json.loads(await cfg_file.read())
    elif config_path.endswith(".yaml") or config_path.endswith(".yml"):
        async with aiofiles.open(config_path) as cfg_file:
            cfg = yaml.load(await cfg_file.read(), yaml.Loader)
    elif config_path.endswith(".xml"):
        async with aiofiles.open(config_path) as cfg_file:
            cfg = xmltodict.parse(await cfg_file.read())
    else:
        raise ValueError("Invalid config file format")
    modfetch = ModFetch(cfg, feature)
    await modfetch.start()


@click.command()
@click.argument("config", type=click.Path(exists=True), default="mods.toml")
@click.option("-f", "--feature", help="Feature to enable")
def cli_main(config, feature=""):
    if feature:
        features = feature.split(",")
    else:
        features = []
    asyncio.run(main(config, features))


if __name__ == "__main__":
    cli_main()
