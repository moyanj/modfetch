"""配置解析基线测试: from_dict 对 toml/yaml/json、继承、默认值的解析行为"""

import json
from pathlib import Path

import pytest
import toml
import yaml

from modfetch.models import (
    FileType,
    ModEntry,
    ModFetchConfig,
    ModLoader,
    MrpackMode,
    OutputFormat,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "configs"


class TestParseToml:
    def test_parse_toml_minimal(self):
        """最小 TOML 配置 → ModFetchConfig，默认值正确"""
        raw = toml.load(FIXTURES / "minimal.toml")
        config = ModFetchConfig.from_dict(raw)

        assert config.minecraft.version == ["1.21.1"]
        assert config.minecraft.mod_loader == ModLoader.FABRIC
        assert config.minecraft.mods == ["sodium"]
        # 默认值
        assert config.max_concurrent == 5
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.output.format == [OutputFormat.MRPACK]
        assert config.output.mrpack_modes == [MrpackMode.DOWNLOAD]
        assert config.metadata.name == "TestPack"

    def test_parse_multi_version(self):
        raw = toml.load(FIXTURES / "multi_version.toml")
        config = ModFetchConfig.from_dict(raw)
        assert config.minecraft.version == ["1.21.1", "1.20.4"]

    def test_parse_multi_loader(self):
        raw = toml.load(FIXTURES / "multi_loader.toml")
        config = ModFetchConfig.from_dict(raw)
        assert config.minecraft.mod_loader == [ModLoader.FABRIC, ModLoader.FORGE]

    def test_parse_mrpack_modes_string(self):
        """mrpack_modes 为字符串时应正确解析为单元素列表"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
                "output": {"mrpack_modes": "reference"},
            }
        )
        assert config.output.mrpack_modes == [MrpackMode.REFERENCE]

    def test_parse_legacy_mrpack_mode(self):
        """兼容旧的 mrpack_mode 单数字段"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
                "output": {"mrpack_mode": "reference"},
            }
        )
        assert config.output.mrpack_modes == [MrpackMode.REFERENCE]


class TestParseYamlJson:
    def test_parse_yaml_inheritance(self):
        """YAML 配置 + from 继承 → 父配置引用正确解析"""
        raw = yaml.safe_load((FIXTURES / "inheritance.yaml").read_text())
        config = ModFetchConfig.from_dict(raw)

        assert config.minecraft.version == ["1.21.1"]
        assert config.minecraft.mods == ["sodium"]
        assert len(config.parent_configs) == 1
        assert config.parent_configs[0].url == "https://example.com/base.toml"
        assert config.parent_configs[0].format == "toml"

    def test_parse_json_format(self):
        """JSON 配置解析 → 与 YAML 等价"""
        raw = json.loads((FIXTURES / "inheritance.json").read_text())
        config = ModFetchConfig.from_dict(raw)

        assert config.minecraft.version == ["1.21.1"]
        assert config.minecraft.mod_loader == ModLoader.FABRIC
        assert config.output.format == [OutputFormat.MRPACK]
        assert len(config.parent_configs) == 1


class TestParseModEntries:
    def test_parse_mod_at_version_syntax(self):
        """slug/id@version 语法解析"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {
                    "version": ["1.21.1"],
                    "mods": ["sodium@0.6.0", "fabric-api"],
                }
            }
        )
        first = config.minecraft.mods[0]
        assert isinstance(first, ModEntry)
        assert first.id == "sodium"
        assert first.version == "0.6.0"
        assert config.minecraft.mods[1] == "fabric-api"

    def test_parse_mod_entry_dict(self):
        raw = toml.load(FIXTURES / "feature_gated.toml")
        config = ModFetchConfig.from_dict(raw)

        gated = config.minecraft.mods[1]
        assert isinstance(gated, ModEntry)
        assert gated.id == "fabric-api"
        assert gated.feature == "opt"

        pinned = config.minecraft.mods[2]
        assert pinned.slug == "sodium"
        assert pinned.version == "0.6.0"
        assert pinned.only_version == "1.21.1"

    def test_parse_invalid_entry_type_raises(self):
        with pytest.raises(ValueError, match="无效的模组条目类型"):
            ModFetchConfig.from_dict(
                {
                    "minecraft": {
                        "version": ["1.21.1"],
                        "mods": [123],
                    }
                }
            )


class TestKnownBugs:
    @pytest.mark.xfail(
        reason="bug: from_dict 的 pop('from') 会修改调用方传入的 dict",
        strict=False,
    )
    def test_from_dict_does_not_mutate_input(self):
        """from_dict 不应修改调用方传入的 dict（回归测试）"""
        raw = {
            "from": [{"url": "https://example.com/base.toml"}],
            "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
        }
        ModFetchConfig.from_dict(raw)
        assert "from" in raw, "输入 dict 被 from_dict 修改了"

    @pytest.mark.xfail(
        reason="bug: format 为字符串时会逐字符遍历导致 ValueError",
        strict=False,
    )
    def test_parse_format_string_not_list(self):
        """format = "mrpack"（字符串而非列表）→ 应正确解析为 [MRPACK]"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
                "output": {"format": "mrpack"},
            }
        )
        assert config.output.format == [OutputFormat.MRPACK]


class TestRoundTrip:
    def test_to_dict_round_trip(self):
        """to_dict → from_dict 应保持关键字段一致"""
        raw = toml.load(FIXTURES / "minimal.toml")
        config = ModFetchConfig.from_dict(raw)
        restored = ModFetchConfig.from_dict(config.to_dict())

        assert restored.minecraft.version == config.minecraft.version
        assert restored.minecraft.mod_loader == config.minecraft.mod_loader
        assert restored.output.format == config.output.format
        assert restored.metadata.name == config.metadata.name

    def test_extra_url_filetype_file(self):
        """extra_urls 中 FileType 默认值"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {
                    "version": ["1.21.1"],
                    "mods": ["sodium"],
                    "extra_urls": [{"url": "https://example.com/a.zip"}],
                }
            }
        )
        assert config.minecraft.extra_urls[0].type == FileType.FILE
