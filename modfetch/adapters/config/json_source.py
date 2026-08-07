"""JSON 配置来源"""

import json
from pathlib import Path
from typing import Any, Mapping


class JsonConfigSource:
    """ConfigSource 的 JSON 实现

    supports() 按文件后缀 .json 判定，load() 解析为嵌套 dict。
    """

    def supports(self, path: Path) -> bool:
        """判断路径后缀是否为 .json（大小写不敏感）"""
        return path.suffix.lower() == ".json"

    def load(self, path: Path) -> Mapping[str, Any]:
        """读取并解析 JSON 文件为配置字典"""
        return json.loads(path.read_text(encoding="utf-8"))
