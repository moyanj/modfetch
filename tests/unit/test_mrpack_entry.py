"""mrpack 文件条目构建基线测试: ModFetchOrchestrator._build_mrpack_entry"""

from modfetch.orchestrator import ModFetchOrchestrator


def _file_info(**overrides) -> dict:
    info = {
        "url": "https://cdn.modrinth.com/data/x/sodium.jar",
        "filename": "sodium.jar",
        "size": 123456,
        "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
    }
    info.update(overrides)
    return info


class TestBuildMrpackEntry:
    def test_entry_format(self):
        """产出字段: path/hashes/env/downloads/fileSize"""
        entry = ModFetchOrchestrator._build_mrpack_entry("mods", _file_info())

        assert entry["path"] == "mods/sodium.jar"
        assert entry["hashes"] == {"sha1": "a" * 40, "sha512": "b" * 128}
        assert entry["downloads"] == ["https://cdn.modrinth.com/data/x/sodium.jar"]
        assert entry["fileSize"] == 123456

    def test_default_env(self):
        """默认环境标记: client/server 均 required"""
        entry = ModFetchOrchestrator._build_mrpack_entry("mods", _file_info())
        assert entry["env"] == {"client": "required", "server": "required"}

    def test_custom_env(self):
        """资源包/光影包使用自定义环境标记"""
        env = {"client": "required", "server": "optional"}
        entry = ModFetchOrchestrator._build_mrpack_entry(
            "resourcepacks", _file_info(), env
        )
        assert entry["env"] == env
        assert entry["path"] == "resourcepacks/sodium.jar"

    def test_missing_optional_fields(self):
        """缺 hashes/size 时使用默认值"""
        entry = ModFetchOrchestrator._build_mrpack_entry(
            "mods", {"url": "https://x/y.jar", "filename": "y.jar"}
        )
        assert entry["hashes"] == {}
        assert entry["fileSize"] == 0
