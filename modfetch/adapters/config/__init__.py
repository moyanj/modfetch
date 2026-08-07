"""配置来源适配器"""

from pathlib import Path

from modfetch.adapters.config.json_source import JsonConfigSource
from modfetch.adapters.config.toml_source import TomlConfigSource
from modfetch.adapters.config.yaml_source import YamlConfigSource
from modfetch.adapters.config.inheritance import (
    load_with_inheritance,
    resolve_inheritance,
)
from modfetch.ports.config_source import ConfigSource


def get_config_source(path: Path) -> ConfigSource:
    """按文件后缀选择配置来源

    Raises:
        ValueError: 不支持的格式
    """
    for source in (TomlConfigSource(), JsonConfigSource(), YamlConfigSource()):
        if source.supports(path):
            return source
    raise ValueError(f"不支持的配置文件格式: {path.suffix}")


__all__ = [
    "TomlConfigSource",
    "YamlConfigSource",
    "JsonConfigSource",
    "get_config_source",
    "load_with_inheritance",
    "resolve_inheritance",
]
