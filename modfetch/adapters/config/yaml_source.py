"""YAML 配置来源"""

from pathlib import Path
from typing import Any, Mapping

import yaml


class YamlConfigSource:
    """ConfigSource 的 YAML 实现"""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in (".yaml", ".yml")

    def load(self, path: Path) -> Mapping[str, Any]:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
