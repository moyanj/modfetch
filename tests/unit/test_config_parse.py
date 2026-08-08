"""配置解析基线测试: from_dict 对 toml/yaml/json、继承、默认值的解析行为"""

import json
from pathlib import Path

import pytest
import yaml

from modfetch.adapters.config.toml_parser import load as load_toml
from modfetch.adapters.config.toml_parser import loads as toml_loads
from modfetch.domain import (
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
        raw = load_toml(FIXTURES / "minimal.toml")
        config = ModFetchConfig.from_dict(raw)

        assert config.minecraft.version == ["1.21.1"]
        assert config.minecraft.mod_loader == ModLoader.FABRIC
        assert config.minecraft.mods == ["sodium"]
        # 默认值
        assert config.max_concurrent == 5
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.verify_ssl is True
        assert config.output.format == [OutputFormat.MRPACK]
        assert config.output.mrpack_modes == [MrpackMode.DOWNLOAD]
        assert config.metadata.name == "TestPack"

    def test_parse_multi_version(self):
        raw = load_toml(FIXTURES / "multi_version.toml")
        config = ModFetchConfig.from_dict(raw)
        assert config.minecraft.version == ["1.21.1", "1.20.4"]

    def test_parse_multi_loader(self):
        raw = load_toml(FIXTURES / "multi_loader.toml")
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
        raw = load_toml(FIXTURES / "feature_gated.toml")
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
    def test_from_dict_does_not_mutate_input(self):
        """from_dict 不应修改调用方传入的 dict（回归测试）"""
        raw = {
            "from": [{"url": "https://example.com/base.toml"}],
            "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
        }
        ModFetchConfig.from_dict(raw)
        assert "from" in raw, "输入 dict 被 from_dict 修改了"

    def test_parse_format_string_not_list(self):
        """format = "mrpack"（字符串而非列表）→ 应正确解析为 [MRPACK]"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
                "output": {"format": "mrpack"},
            }
        )
        assert config.output.format == [OutputFormat.MRPACK]

    def test_toml_heterogeneous_mods_array(self):
        """TOML mods 数组混写 dict 与字符串 → 完整解析（回归: 旧 toml 库要求同构）"""
        raw = toml_loads(
            "[minecraft]\n"
            'version = ["1.21.1"]\n'
            'mod_loader = "fabric"\n'
            "mods = [\n"
            '    { id = "sodium", feature = "performance" },\n'
            '    "rei"\n'
            "]\n"
        )
        config = ModFetchConfig.from_dict(raw)
        assert len(config.minecraft.mods) == 2
        assert isinstance(config.minecraft.mods[0], ModEntry)
        assert config.minecraft.mods[0].id == "sodium"
        assert config.minecraft.mods[1] == "rei"

    def test_toml_root_keys_before_tables(self):
        """根表键放在 [table] 之前 → toml 解析完整（旧 toml 库会静默丢弃）"""
        raw = toml_loads(
            'max_concurrent = 10\nfeatures = ["perf"]\n'
            "[metadata]\nname = \"x\""
        )
        # 顶层键完整保留（回归: 旧 toml 库读文件时根表键被并入子表丢失）
        assert raw["max_concurrent"] == 10
        assert raw["features"] == ["perf"]
        assert raw["metadata"] == {"name": "x"}


class TestRoundTrip:
    def test_to_dict_round_trip(self):
        """to_dict → from_dict 应保持关键字段一致"""
        raw = load_toml(FIXTURES / "minimal.toml")
        config = ModFetchConfig.from_dict(raw)
        restored = ModFetchConfig.from_dict(config.to_dict())

        assert restored.minecraft.version == config.minecraft.version
        assert restored.minecraft.mod_loader == config.minecraft.mod_loader
        assert restored.output.format == config.output.format
        assert restored.metadata.name == config.metadata.name
        # verify_ssl 必须保留（round-trip 不丢配置）
        assert restored.verify_ssl == config.verify_ssl

    def test_parse_verify_ssl_false(self):
        """verify_ssl=false 应被 from_dict 读取（不回退默认 True）"""
        config = ModFetchConfig.from_dict(
            {
                "minecraft": {"version": ["1.21.1"], "mods": ["sodium"]},
                "verify_ssl": False,
            }
        )
        assert config.verify_ssl is False

    def test_verify_ssl_default_true(self):
        """未配置 verify_ssl 时默认 True"""
        config = ModFetchConfig.from_dict(
            {"minecraft": {"version": ["1.21.1"], "mods": ["sodium"]}}
        )
        assert config.verify_ssl is True

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
