"""extra_urls 解析基线测试

目标目录语义（file→根目录、shaderpack→shaderpacks/ 等）由
integration/test_build_service.py 的 extra_url 端到端用例覆盖，
此处仅锁定配置解析层契约。
"""

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
        assert first.type == FileType.FILE  # type 缺省默认 FILE
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

    def test_filename_fallback_to_url_basename(self):
        """filename 缺省时取 URL 末段"""
        entry = ExtraUrl(url="https://example.com/a/b/config.toml")
        assert entry.filename == "config.toml"
