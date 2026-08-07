"""extra_urls 解析与目标目录基线测试"""

from pathlib import Path

import pytest

from modfetch.adapters.config.toml_parser import load as load_toml
from modfetch.domain import ExtraUrl, FileType, ModFetchConfig

FIXTURES = Path(__file__).parent.parent / "fixtures" / "configs"


class TestExtraUrlParse:
    def test_parse_fixture(self):
        raw = load_toml(FIXTURES / "extra_urls.toml")
        config = ModFetchConfig.from_dict(raw)

        urls = config.minecraft.extra_urls
        assert len(urls) == 3

        first = urls[0]
        assert first.type == FileType.FILE
        assert first.sha1 == "deadbeef"
        assert first.filename == "datapack.zip"  # 自动提取

        second = urls[1]
        assert second.type == FileType.RESOURCEPACK
        assert second.only_version == "1.21.1"
        assert second.filename == "cool-pack.zip"

        third = urls[2]
        assert third.type == FileType.SHADERPACK
        assert third.filename == "seus.zip"  # 显式指定优先
        assert third.feature == "shaders"

    def test_invalid_entry_type_raises(self):
        with pytest.raises(ValueError, match="无效的 extra_urls"):
            ModFetchConfig.from_dict(
                {
                    "minecraft": {
                        "version": ["1.21.1"],
                        "mods": ["sodium"],
                        "extra_urls": ["not-a-dict"],
                    }
                }
            )

    def test_invalid_file_type_raises(self):
        with pytest.raises(ValueError):
            ModFetchConfig.from_dict(
                {
                    "minecraft": {
                        "version": ["1.21.1"],
                        "mods": ["sodium"],
                        "extra_urls": [
                            {"url": "https://x/y.zip", "type": "bogus"}
                        ],
                    }
                }
            )


class TestExtraUrlDestination:
    """目标目录约定（orchestrator._process_extra_urls 的参考语义）"""

    @pytest.mark.parametrize(
        "file_type,expected_category",
        [
            (FileType.FILE, "file"),
            # 当前行为基线: MOD 类型映射为 "mod"（单数，orchestrator 的 replace 逻辑所致）
            (FileType.MOD, "mod"),
            (FileType.RESOURCEPACK, "resourcepacks"),
            (FileType.SHADERPACK, "shaderpacks"),
        ],
    )
    def test_category_mapping(self, file_type, expected_category):
        """file 类型放版本根目录，其他类型进入对应子目录（pack→packs 复数化）"""
        if file_type == FileType.FILE:
            category = "file"
        else:
            category = file_type.value.replace("pack", "packs")
        assert category == expected_category

    def test_url_basename_strips_trailing_slash(self):
        """从 URL 提取文件名时去掉尾部斜杠"""
        url = "https://example.com/dir/"
        basename = url.rstrip("/").split("/")[-1]
        assert basename == "dir"

    def test_filename_fallback_to_url(self):
        entry = ExtraUrl(url="https://example.com/a/b/config.toml")
        assert entry.filename == "config.toml"
