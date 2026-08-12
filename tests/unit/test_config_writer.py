"""配置写回适配器单元测试（add 命令的落盘层）

覆盖：
- TOML：增量追加保留注释/格式、重复跳过（含 slug@version）、
  缺失 minecraft/mods 时创建结构
- YAML / JSON：全量重写追加
- 不支持格式报错
"""

import json
from pathlib import Path

import pytest
import yaml

from modfetch.adapters.config.writer import add_mod_entry


def test_toml_appends_and_preserves_comments(tmp_path):
    """TOML 追加保留注释与既有条目，slug 追加到列表末尾"""
    p = tmp_path / "mods.toml"
    p.write_text(
        "# 我的配置\n"
        "[minecraft]\n"
        'version = ["1.21.1"]\n'
        'mods = ["sodium"]\n',
        encoding="utf-8",
    )
    assert add_mod_entry(p, "fabric-api") is True
    content = p.read_text(encoding="utf-8")
    assert "# 我的配置" in content  # 注释保留
    assert 'mods = ["sodium", "fabric-api"]' in content


def test_toml_duplicate_skips(tmp_path):
    """已含纯 slug → 返回 False 且文件不变"""
    p = tmp_path / "mods.toml"
    p.write_text('[minecraft]\nmods = ["sodium"]\n', encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert add_mod_entry(p, "sodium") is False
    assert p.read_text(encoding="utf-8") == before


def test_toml_duplicate_slug_version_skips(tmp_path):
    """已含 slug@version 形式 → 视为重复跳过"""
    p = tmp_path / "mods.toml"
    p.write_text('[minecraft]\nmods = ["modmenu@2.5.0"]\n', encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert add_mod_entry(p, "modmenu") is False
    assert p.read_text(encoding="utf-8") == before


def test_toml_creates_missing_structure(tmp_path):
    """无 [minecraft] 或 mods 字段 → 自动创建结构"""
    p = tmp_path / "mods.toml"
    p.write_text("[output]\ndownload_dir = \"downloads\"\n", encoding="utf-8")
    assert add_mod_entry(p, "sodium") is True
    content = p.read_text(encoding="utf-8")
    assert "[minecraft]" in content
    assert 'mods = ["sodium"]' in content
    # 原 [output] 保留
    assert 'download_dir = "downloads"' in content


def test_yaml_appends(tmp_path):
    """YAML 全量重写追加"""
    p = tmp_path / "mods.yaml"
    p.write_text("minecraft:\n  mods:\n    - sodium\n", encoding="utf-8")
    assert add_mod_entry(p, "fabric-api") is True
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["minecraft"]["mods"] == ["sodium", "fabric-api"]


def test_yaml_duplicate_skips(tmp_path):
    """YAML 已含 slug → 跳过"""
    p = tmp_path / "mods.yaml"
    p.write_text("minecraft:\n  mods:\n    - sodium\n", encoding="utf-8")
    assert add_mod_entry(p, "sodium") is False


def test_json_appends(tmp_path):
    """JSON 全量重写追加（规范缩进 + 换行）"""
    p = tmp_path / "mods.json"
    p.write_text('{"minecraft": {"mods": ["sodium"]}}', encoding="utf-8")
    assert add_mod_entry(p, "fabric-api") is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["minecraft"]["mods"] == ["sodium", "fabric-api"]
    assert p.read_text(encoding="utf-8").endswith("\n")


def test_unsupported_format_raises(tmp_path):
    """未知后缀 → ValueError"""
    p = tmp_path / "mods.toml.bak"
    p.write_text("whatever", encoding="utf-8")
    with pytest.raises(ValueError, match="不支持的配置文件格式"):
        add_mod_entry(p, "sodium")