"""配置文件写回适配器（add 命令用）

与只读的 ConfigSource 不同，这里提供「修改并保存」能力：
- TOML 用 tomlkit 直接解析文档对象、增量追加后整体 dump —— 保留
  原文件注释与书写格式（面向用户手写配置的关键要求，避免
  ``ModFetchConfig.to_dict()`` 全量重建破坏风格）
- YAML/JSON 全量重写（无法保留注释，输出为规范格式）

不依赖 domain 层：在原始 dict/文档层面增量操作，写回后再由
调用方重新解析校验。
"""

from pathlib import Path
from typing import List

import tomlkit
import yaml


def add_mod_entry(path: Path, slug: str) -> bool:
    """把模组 slug 追加到配置文件 minecraft.mods 列表

    Args:
        path: 配置文件路径（.toml / .yaml / .yml / .json）
        slug: 要添加的模组 slug 或 ID

    Returns:
        True 表示已成功追加；False 表示该 slug 已存在于 mods 列表（未改动）

    Raises:
        ValueError: 不支持的配置格式，或文件解析失败
    """
    if path.suffix.lower() == ".toml":
        return _add_toml(path, slug)
    if path.suffix.lower() in (".yaml", ".yml"):
        return _add_yaml(path, slug)
    if path.suffix.lower() == ".json":
        return _add_json(path, slug)
    raise ValueError(f"不支持的配置文件格式: {path.suffix}")


def _contains_slug(mods: List[object], slug: str) -> bool:
    """判断 mods 数组是否已包含该 slug

    条目可能为纯字符串、``slug@version`` 字符串或 dict（ModEntry）。
    仅对字符串条目做 slug 比对（``slug@ver`` 拆出 slug 部分）；
    dict 条目因结构复杂不做去重判断（保守地视为不重复）。
    """
    for entry in mods:
        if isinstance(entry, str):
            if "@" in entry and entry.split("@", 1)[0] == slug:
                return True
            if entry == slug:
                return True
    return False


def _add_toml(path: Path, slug: str) -> bool:
    """TOML：tomlkit 文档对象增量追加（保留注释与格式）"""
    document = tomlkit.parse(path.read_text(encoding="utf-8"))
    if "minecraft" not in document:
        document["minecraft"] = tomlkit.table()
    minecraft = document["minecraft"]
    if "mods" not in minecraft:
        minecraft["mods"] = tomlkit.array()
    mods = minecraft["mods"]
    if _contains_slug(list(mods), slug):
        return False
    mods.append(slug)
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return True


def _add_yaml(path: Path, slug: str) -> bool:
    """YAML：全量重写（追加到 minecraft.mods 数组）"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mods = raw.setdefault("minecraft", {}).setdefault("mods", [])
    if _contains_slug(mods, slug):
        return False
    mods.append(slug)
    path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


def _add_json(path: Path, slug: str) -> bool:
    """JSON：全量重写（追加到 minecraft.mods 数组）"""
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    mods = raw.setdefault("minecraft", {}).setdefault("mods", [])
    if _contains_slug(mods, slug):
        return False
    mods.append(slug)
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True
