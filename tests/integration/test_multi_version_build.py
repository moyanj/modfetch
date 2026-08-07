"""多版本×多加载器构建基线测试"""

import json
import zipfile
from pathlib import Path

import pytest

from modfetch.models import ModFetchConfig
from modfetch.orchestrator import ModFetchOrchestrator

pytestmark = pytest.mark.usefixtures("mock_modrinth")


async def _run(config_dict: dict) -> Path:
    config = ModFetchConfig.from_dict(config_dict)
    await ModFetchOrchestrator(config).run()
    return Path(config.output.download_dir)


class TestMultiVersion:
    async def test_two_versions(self, make_config_dict):
        """两个 MC 版本 → 两个独立下载目录 + 两个 mrpack"""
        download_dir = await _run(
            make_config_dict(
                minecraft={"version": ["1.21.1", "1.20.4"], "mod_loader": "fabric"}
            )
        )

        for version in ("1.21.1", "1.20.4"):
            mods_dir = download_dir / f"{version}-fabric" / "mods"
            assert (mods_dir / "sodium-fabric-0.6.0.jar").exists()
            assert (
                download_dir / f"TestPack_1.0.0_MC{version}-fabric.mrpack"
            ).exists()

    async def test_two_loaders(self, make_config_dict):
        """两个加载器 → 两个独立目录，各自包含完整依赖树"""
        download_dir = await _run(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1"],
                    "mod_loader": ["fabric", "forge"],
                }
            )
        )

        for loader in ("fabric", "forge"):
            mods_dir = download_dir / f"1.21.1-{loader}" / "mods"
            assert (mods_dir / "sodium-fabric-0.6.0.jar").exists()
            assert (mods_dir / "fabric-api-0.100.0.jar").exists()

    async def test_cartesian_product(self, make_config_dict):
        """2 版本 × 2 加载器 = 4 组输出"""
        download_dir = await _run(
            make_config_dict(
                minecraft={
                    "version": ["1.21.1", "1.20.4"],
                    "mod_loader": ["fabric", "forge"],
                }
            )
        )

        mrpacks = list(download_dir.glob("*.mrpack"))
        assert len(mrpacks) == 4

        for version in ("1.21.1", "1.20.4"):
            for loader in ("fabric", "forge"):
                assert (download_dir / f"{version}-{loader}").is_dir()
                mrpack = (
                    download_dir / f"TestPack_1.0.0_MC{version}-{loader}.mrpack"
                )
                assert mrpack.exists()
                with zipfile.ZipFile(mrpack) as zf:
                    manifest = json.loads(zf.read("modrinth.index.json"))
                    assert manifest["dependencies"]["minecraft"] == version

    async def test_version_state_isolation(self, make_config_dict):
        """每个 (version, loader) 组合状态独立重置（依赖树重复出现是预期行为）"""
        download_dir = await _run(
            make_config_dict(
                minecraft={"version": ["1.21.1", "1.20.4"], "mod_loader": "fabric"}
            )
        )
        # 两个版本目录各自独立包含完整模组集
        for version in ("1.21.1", "1.20.4"):
            mods = list((download_dir / f"{version}-fabric" / "mods").glob("*.jar"))
            assert len(mods) == 2
