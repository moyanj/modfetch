"""YAML 配置来源"""

from pathlib import Path
from typing import Any, Mapping

import yaml


class YamlConfigSource:
    """ConfigSource 的 YAML 实现

    supports() 接受 .yaml/.yml 两种后缀；load() 使用 yaml.safe_load
    （不执行任意标签，避免反序列化风险）。
    """

    def supports(self, path: Path) -> bool:
        """判断路径后缀是否为 .yaml/.yml（大小写不敏感）"""
        return path.suffix.lower() in (".yaml", ".yml")

    def load(self, path: Path) -> Mapping[str, Any]:
        """读取并安全解析 YAML 文件为配置字典"""
        return yaml.safe_load(path.read_text(encoding="utf-8"))
