"""配置继承解析测试（file:// 本地父配置 + 合并语义）"""

from pathlib import Path

import aiohttp
import pytest

from modfetch.adapters.config import load_with_inheritance, resolve_inheritance
from modfetch.domain.config_models import ModLoader, ModFetchConfig, ParentConfig


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


async def test_inheritance_self_cycle_detected(tmp_path: Path):
    """自循环引用（A→A）→ ValueError，避免无限递归"""
    base = tmp_path / "base.toml"
    base.write_text(
        f'from = [{{ url = "{base.as_uri()}", format = "toml" }}]\n'
        '[minecraft]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    child = {"from": [{"url": base.as_uri(), "format": "toml"}]}

    with pytest.raises(ValueError, match="循环引用"):
        await resolve_inheritance(child)


async def test_inheritance_mutual_cycle_detected(tmp_path: Path):
    """相互循环（A→B→A）→ ValueError"""
    a = tmp_path / "a.toml"
    b = tmp_path / "b.toml"
    a.write_text(
        f'from = [{{ url = "{b.as_uri()}", format = "toml" }}]\n',
        encoding="utf-8",
    )
    b.write_text(
        f'from = [{{ url = "{a.as_uri()}", format = "toml" }}]\n',
        encoding="utf-8",
    )
    child = {"from": [{"url": a.as_uri(), "format": "toml"}]}

    with pytest.raises(ValueError, match="循环引用"):
        await resolve_inheritance(child)


async def test_inheritance_diamond_is_allowed(tmp_path: Path):
    """菱形继承（A←B、A←C、B/C←D）不误报循环"""
    a = tmp_path / "a.toml"
    a.write_text(
        '[minecraft]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    b = tmp_path / "b.toml"
    b.write_text(
        f'from = [{{ url = "{a.as_uri()}", format = "toml" }}]\n',
        encoding="utf-8",
    )
    c = tmp_path / "c.toml"
    c.write_text(
        f'from = [{{ url = "{a.as_uri()}", format = "toml" }}]\n'
        '[minecraft]\n'
        'mods = ["modmenu"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [
            {"url": b.as_uri(), "format": "toml"},
            {"url": c.as_uri(), "format": "toml"},
        ],
        "minecraft": {"mods": ["fabric-api"]},
    }

    # 不应抛循环异常；a 被多条分支复用（每分支独立追踪）
    merged = await resolve_inheritance(child)
    assert set(merged["minecraft"]["mods"]) >= {"sodium", "modmenu", "fabric-api"}


async def test_inheritance_file_relative_to_config_dir(tmp_path: Path):
    """file:// 相对路径基于引用方配置文件所在目录解析（非 CWD）"""
    sub = tmp_path / "sub"
    sub.mkdir()
    # 基准测试目录之外存在同名文件，用于证明不是从 CWD 解析
    decoy = tmp_path / "base.toml"
    decoy.write_text(
        '[minecraft]\n'
        'mods = ["decoy"]\n',
        encoding="utf-8",
    )
    base = sub / "base.toml"
    base.write_text(
        '[minecraft]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": "file://./base.toml", "format": "toml"}],
    }

    # 传入 base_path=sub → 应解析到 sub/base.toml（sodium），而非 decoy
    merged = await resolve_inheritance(child, _base_path=sub)

    assert merged["minecraft"]["mods"] == ["sodium"]


async def test_inheritance_file_relative_in_nested_chain(tmp_path: Path):
    """链式继承的相对路径逐级以父配置所在目录为基准"""
    leaf_dir = tmp_path / "leaf"
    leaf_dir.mkdir()
    leaf = leaf_dir / "base.toml"
    leaf.write_text(
        '[minecraft]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    mid_dir = tmp_path / "mid"
    mid_dir.mkdir()
    mid = mid_dir / "mid.toml"
    # mid 用相对路径引用 ../leaf/base.toml → 基于 mid 所在目录（mid_dir）
    mid.write_text(
        'from = [{ url = "file://../leaf/base.toml", format = "toml" }]\n'
        '[minecraft]\n'
        'mods = ["modmenu"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": "file://./mid.toml", "format": "toml"}],
    }

    # 顶层 child 的 base_path = mid_dir（child 配置文件所在目录）
    # → 先解析 mid.toml；其自身又从 mid_dir 找 ../leaf/base.toml 迭代寻址
    merged = await resolve_inheritance(child, _base_path=mid_dir)

    assert merged["minecraft"]["mods"] == ["sodium", "modmenu"]


async def test_inheritance_xml_rejected():
    """xml 格式声明但未实现解析器 → ParentConfig 拒绝"""
    with pytest.raises(ValueError, match="不支持配置格式"):
        ParentConfig(url="file://base.xml", format="xml")


async def test_inheritance_merge_hash_dedup_handles_dict_and_string(tmp_path: Path):
    """去重基于内容哈希：父串、子 dict 指向同一模组 → 只保留一份 """
    base = tmp_path / "base.toml"
    base.write_text(
        '[minecraft]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    child = {
        "from": [{"url": base.as_uri(), "format": "toml"}],
        # dict 形式的同模组（内容等价于字符串 sodium）应被哈希去重
        "minecraft": {"mods": [{"id": "sodium"}]},
    }

    merged = await resolve_inheritance(child)

    # 父配置的字符串项在前，被保留；子 dict 形式的同模组去重掉
    assert merged["minecraft"]["mods"] == ["sodium"]

    # 反向验证：子 dict 带 version → 仍因标识 "sodium" 相同被去重
    child_rev = {
        "from": [{"url": base.as_uri(), "format": "toml"}],
        "minecraft": {"mods": [{"id": "sodium", "version": "1.7"}]},
    }
    merged_rev = await resolve_inheritance(child_rev)
    assert merged_rev["minecraft"]["mods"] == ["sodium"]


async def test_inheritance_merge_hash_dedup_keeps_distinct(tmp_path: Path):
    """内容不同的列表项被哈希去重时不影响顺序与保留了"""
    result = ModFetchConfig.merge_dicts(
        {"minecraft": {"mods": ["a", "b"]}},
        {"minecraft": {"mods": ["b", "c", "a"]}},
    )
    # 保持首次出现顺序，重复项丢弃
    assert result["minecraft"]["mods"] == ["a", "b", "c"]