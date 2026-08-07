"""JSON 配置来源"""

import json
from pathlib import Path
from typing import Any, Mapping


class JsonConfigSource:
    """ConfigSource 的 JSON 实现"""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    def load(self, path: Path) -> Mapping[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
