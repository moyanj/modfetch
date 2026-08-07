"""端到端构建基线测试: config → 解析 → 依赖 → 下载(file://) → mrpack

依赖图谱: sodium --required--> fabric-api
全部通过 mock_modrinth 离线完成。
"""

import json
import zipfile
from pathlib import Path

import pytest

from modfetch.models import ModFetchConfig
from modfetch.orchestrator import ModFetchOrchestrator

pytestmark = pytest.mark.usefixtures("mock_modrinth")


async def _run_build(config_dict: dict) -> tuple[ModFetchOrchestrator, Path]:
    config = ModFetchConfig.from_dict(config_dict)
    orchestrator = ModFetchOrchestrator(config)
    await orchestrator.run()
    return orchestrator, Path(config.output.download_dir)


class TestFullBuild:
    async def test_end_to_end_mrpack(self, make_config_dict):
        """完整链路: 解析 sodium + 递归依赖 fabric-api → 下载 → mrpack"""
        _, download_dir = await _run_build(make_config_dict())

        mods_dir = download_dir / "1.21.1-fabric" / "mods"
        assert (mods_dir / "sodium-fabric-0.6.0.jar").exists()
        # 依赖被递归解析并下载
        assert (mods_dir / "fabric-api-0.100.0.jar").exists()

        mrpack = download_dir / "TestPack_1.0.0_MC1.21.1-fabric.mrpack"
        assert mrpack.exists()

        # mrpack 内容: manifest + overrides
        with zipfile.ZipFile(mrpack) as zf:
            names = zf.namelist()
            assert "modrinth.index.json" in names
            assert "overrides/mods/sodium-fabric-0.6.0.jar" in names

            manifest = json.loads(zf.read("modrinth.index.json"))
            assert manifest["name"] == "TestPack"
            assert manifest["dependencies"]["minecraft"] == "1.21.1"
            assert manifest["dependencies"]["fabric-loader"] == "0.16.5"
            # DOWNLOAD 模式: manifest.files 为空
            assert manifest["files"] == []

    async def test_reference_mode_manifest(self, make_config_dict):
        """REFERENCE 模式: manifest.files 含下载引用，overrides 无模组"""
        _, download_dir = await _run_build(
            make_config_dict(output={"mrpack_modes": ["reference"]})
        )

        mrpack = download_dir / "TestPack_1.0.0_MC1.21.1-fabric.mrpack"
        assert mrpack.exists()

        with zipfile.ZipFile(mrpack) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
            paths = {f["path"] for f in manifest["files"]}
            assert "mods/sodium-fabric-0.6.0.jar" in paths
            assert "mods/fabric-api-0.100.0.jar" in paths
            for f in manifest["files"]:
                assert f["downloads"], "REFERENCE 条目必须带 downloads"
                assert f["env"] == {"client": "required", "server": "required"}

            # REFERENCE 模式下 overrides 不包含模组文件
            names = zf.namelist()
            assert not any(
                n.startswith("overrides/mods/") for n in names
            )

    async def test_zip_output(self, make_config_dict):
        """ZIP 格式输出"""
        _, download_dir = await _run_build(
            make_config_dict(output={"format": ["zip"]})
        )

        archive = download_dir / "archive-1.21.1-fabric.zip"
        assert archive.exists()
        with zipfile.ZipFile(archive) as zf:
            assert any("sodium-fabric-0.6.0.jar" in n for n in zf.namelist())

    async def test_orchestrator_stats(self, make_config_dict):
        """统计: sodium + fabric-api 依赖 = 2 个已处理模组"""
        orchestrator, _ = await _run_build(make_config_dict())
        stats = orchestrator.get_stats()
        assert stats["processed_mods"] == 2
        assert stats["skipped"] == []

    async def test_unresolvable_mod_skipped(self, make_config_dict):
        """无法解析的模组被跳过而非失败（当前行为基线）"""
        orchestrator, _ = await _run_build(
            make_config_dict(minecraft={"mods": ["sodium", "ghost-mod"]})
        )
        stats = orchestrator.get_stats()
        assert "ghost-mod" in stats["skipped"]
        assert stats["processed_mods"] == 2
