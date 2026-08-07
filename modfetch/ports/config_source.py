"""配置来源端口"""

from pathlib import Path
from typing import Any, Mapping, Protocol


class ConfigSource(Protocol):
    """配置文件加载接口（按格式解析为裸 Mapping）"""

    def load(self, path: Path) -> Mapping[str, Any]:
        ...

    def supports(self, path: Path) -> bool:
        """是否支持该文件格式"""
        ...
