"""配置继承解析测试（file:// 本地父配置 + 合并语义）"""

from pathlib import Path

import aiohttp
import pytest

from modfetch.adapters.config import load_with_inheritance, resolve_inheritance
from modfetch.domain.config_models import ModLoader, ModFetchConfig


async def test_resolve_inheritance_local_file(tmp_path: Path):
    """file:// 本地父配置：版本/加载器沿用父值，mods 列表拼接"""
    base = tmp_path / "base.toml"
    base.write_text(
        '[minecraft]\n'
        'version = ["1.21.1"]\n'
        'mod_loader = "fabric"\n'
        'mods = ["sodium", "modmenu"]\n'
        '[metadata]\n'
        'name = "Base Pack"\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "toml"}],
        "minecraft": {"mods": ["fabric-api"]},
    }

    merged = await resolve_inheritance(child)

    # 父配置的 mods 与子配置拼接去重（保持顺序）
    assert merged["minecraft"]["mods"] == ["sodium", "modmenu", "fabric-api"]
    # 标量父值沿用（子未覆盖）
    assert merged["minecraft"]["version"] == ["1.21.1"]
    assert merged["minecraft"]["mod_loader"] == "fabric"
    assert merged["metadata"]["name"] == "Base Pack"


async def test_inheritance_child_overrides_scalar(tmp_path: Path):
    """子配置的标量字段覆盖父配置；list 字段按拼接去重语义合并"""
    base = tmp_path / "base.yml"
    base.write_text(
        "minecraft:\n"
        '  version: ["1.20.4"]\n'
        '  mod_loader: "forge"\n'
        '  mods: ["sodium"]\n'
        "metadata:\n"
        '  name: "Base"\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "yaml"}],
        "minecraft": {
            "version": ["1.21.1"],
            "mod_loader": "fabric",
        },
        "metadata": {"name": "Child"},
    }

    merged = await resolve_inheritance(child)

    # list 拼接去重（保持顺序）：父在前、子在后
    assert merged["minecraft"]["version"] == ["1.20.4", "1.21.1"]
    # 标量覆盖：mod_loader 与 metadata.name 由子覆盖
    assert merged["minecraft"]["mod_loader"] == "fabric"
    assert merged["metadata"]["name"] == "Child"
    # 子未覆盖的 mods 仍来自父
    assert "sodium" in merged["minecraft"]["mods"]


async def test_inheritance_recursive(tmp_path: Path):
    """父配置自身含 from 引用 → 递归解析"""
    root = tmp_path / "root.toml"
    root.write_text(
        '[minecraft]\n'
        'version = ["1.21.1"]\n'
        'mod_loader = "fabric"\n'
        'mods = ["modmenu"]\n'
        '[metadata]\n'
        'name = "Root"\n',
        encoding="utf-8",
    )
    base = tmp_path / "base.toml"
    base.write_text(
        f'from = [{{ url = "{root.as_uri()}", format = "toml" }}]\n'
        '[minecraft]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "toml"}],
        "minecraft": {"mods": ["fabric-api"]},
    }

    merged = await resolve_inheritance(child)

    # 三层合并：root 的 mods → base 追加 sodium → child 追加 fabric-api
    assert merged["minecraft"]["mods"] == ["modmenu", "sodium", "fabric-api"]
    assert merged["minecraft"]["version"] == ["1.21.1"]
    assert merged["metadata"]["name"] == "Root"


async def test_inheritance_file_no_session_created(tmp_path: Path, monkeypatch):
    """file:// 继承不需要创建 aiohttp session（重建 session 依赖为零）"""
    base = tmp_path / "base.json"
    base.write_text(
        '{"minecraft": {"version": ["1.21.1"], "mod_loader": "fabric"}}',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "json"}],
    }

    created: list = []

    def _spy_session(*args, **kwargs):
        created.append(True)
        return aiohttp.ClientSession(*args, **kwargs)

    monkeypatch.setattr(aiohttp, "ClientSession", _spy_session)
    merged = await resolve_inheritance(child)

    assert merged["minecraft"]["version"] == ["1.21.1"]
    assert created == [], "纯 file:// 继承不应创建网络会话"


async def test_load_with_inheritance_returns_config(tmp_path: Path):
    """load_with_inheritance 返回完整 ModFetchConfig（含合并内容）"""
    base = tmp_path / "base.toml"
    base.write_text(
        '[minecraft]\n'
        'version = ["1.21.1"]\n'
        'mod_loader = "fabric"\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "toml"}],
        "minecraft": {"mods": ["modmenu"]},
    }

    config = await load_with_inheritance(child)

    assert isinstance(config, ModFetchConfig)
    assert config.minecraft.version == ["1.21.1"]
    assert config.minecraft.mod_loader == ModLoader.FABRIC
    assert set(config.minecraft.mods) >= {"sodium", "modmenu"}


async def test_inheritance_missing_local_file_raises(tmp_path: Path):
    """本地父配置不存在 → ValueError（可诊断而非静默）"""
    child = {
        "from": [{"url": (tmp_path / "ghost.toml").as_uri(), "format": "toml"}],
    }

    with pytest.raises(ValueError, match="父配置文件不存在"):
        await resolve_inheritance(child)