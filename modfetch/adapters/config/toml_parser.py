"""统一 TOML 解析入口

兼容 Python 3.10（无内置 tomllib）与 3.11+：
- 3.11+ 用标准库 `tomllib`（TOML 1.0 规范实现）
- 3.10 用 `tomli`（tomllib 的官方 backport，行为一致）

目的: 替换旧的 `toml` 库。`toml<=0.10` 对数组要求同构
（全是 dict 或全是标量），导致 `mods = [ { … }, "string" ]`
这类异构数组解析失败；本模块统一走 TOML 1.0 规范的
`tomllib`/`tomli`，支持异构数组，与其他标准同。

对外暴露 `load(path) -> dict` 与 `loads(text) -> dict`，
与旧 `toml` 库同名 API 一致，调用方无需感知底层实现差异。
"""

from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib as _toml  # Python >= 3.11
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 分支
    import tomli as _toml  # type: ignore[no-redef]


def load(path: Path) -> Mapping[str, Any]:
    """读取并按 TOML 1.0 规范解析文件内容为 dict"""
    with path.open("rb") as f:
        return _toml.load(f)


def loads(text: str) -> dict:
    """解析 TOML 字符串为 dict"""
    return _toml.loads(text)