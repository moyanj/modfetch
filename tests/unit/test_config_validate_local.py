"""本地校验基线测试: ModFetchConfig.validate() 与构造期 __post_init__ 校验"""

import pytest

from modfetch.models import (
    ExtraUrl,
    MinecraftConfig,
    ModEntry,
    ModFetchConfig,
    ParentConfig,
)


def _make_config(**mc_overrides) -> ModFetchConfig:
    mc = {"version": ["1.21.1"], "mods": ["sodium"], **mc_overrides}
    return ModFetchConfig.from_dict({"minecraft": mc})


class TestValidate:
    def test_validate_missing_version_raises(self):
        """minecraft.version 为空 → 构造期即抛出 ValueError"""
        with pytest.raises(ValueError, match="version"):
            ModFetchConfig.from_dict({"minecraft": {"mods": ["sodium"]}})

    def test_validate_no_content_raises(self):
        """mods/resourcepacks/shaderpacks/extra_urls 全空 → ValueError"""
        with pytest.raises(ValueError, match="至少一个"):
            ModFetchConfig.from_dict({"minecraft": {"version": ["1.21.1"]}})

    def test_validate_invalid_loader_raises(self):
        """mod_loader = 'unknown' → 枚举转换期抛出 ValueError"""
        with pytest.raises(ValueError):
            ModFetchConfig.from_dict(
                {
                    "minecraft": {
                        "version": ["1.21.1"],
                        "mod_loader": "unknown",
                        "mods": ["sodium"],
                    }
                }
            )

    def test_validate_mod_entry_without_id_or_slug_raises(self):
        """ModEntry 既无 id 也无 slug → ValueError"""
        with pytest.raises(ValueError, match="id 或 slug"):
            ModEntry()

    def test_validate_happy_path(self):
        """合法配置 validate() 不抛异常"""
        _make_config().validate()

    def test_validate_multi_loader(self):
        _make_config(mod_loader=["fabric", "forge"]).validate()


class TestPostInit:
    def test_extra_url_requires_url(self):
        with pytest.raises(ValueError, match="url"):
            ExtraUrl()

    def test_extra_url_auto_filename(self):
        """filename 缺省时从 URL 末尾提取"""
        entry = ExtraUrl(url="https://example.com/dir/pack.zip")
        assert entry.filename == "pack.zip"

    def test_parent_config_requires_url(self):
        with pytest.raises(ValueError, match="url"):
            ParentConfig()

    def test_parent_config_invalid_format(self):
        with pytest.raises(ValueError, match="不支持"):
            ParentConfig(url="https://example.com/x", format="ini")

    def test_minecraft_config_requires_content(self):
        with pytest.raises(ValueError):
            MinecraftConfig(version=["1.21.1"])
