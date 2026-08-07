"""TOML 配置来源"""

from pathlib import Path
from typing import Any, Mapping

import toml


class TomlConfigSource:
    """ConfigSource 的 TOML 实现"""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".toml"

    def load(self, path: Path) -> Mapping[str, Any]:
        return toml.load(str(path))
