"""TOML 配置来源"""

from pathlib import Path
from typing import Any, Mapping

import toml


class TomlConfigSource:
    """ConfigSource 的 TOML 实现

    supports() 按文件后缀 .toml 判定，load() 解析为嵌套 dict。
    """

    def supports(self, path: Path) -> bool:
        """判断路径后缀是否为 .toml（大小写不敏感）"""
        return path.suffix.lower() == ".toml"

    def load(self, path: Path) -> Mapping[str, Any]:
        """读取并解析 TOML 文件为配置字典"""
        return toml.load(str(path))
