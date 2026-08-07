"""配置来源端口"""

from pathlib import Path
from typing import Any, Mapping, Protocol


class ConfigSource(Protocol):
    """配置文件加载接口（按格式解析为裸 Mapping）

    契约约定：load 为同步语义，解析失败应抛出可诊断异常（如 ValueError）。
    """

    def load(self, path: Path) -> Mapping[str, Any]:
        """加载并解析配置文件为裸 Mapping

        实现期望：
            - 读取 path 并按自身格式（TOML/YAML/JSON）解析为嵌套 Mapping
            - 文件不存在或格式非法时抛出异常，禁止返回空/部分结果
        """
        ...

    def supports(self, path: Path) -> bool:
        """是否支持该文件格式

        实现期望：依据扩展名或内容判断，返回该实现能否解析 path
        """
        ...
