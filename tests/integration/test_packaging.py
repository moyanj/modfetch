"""打包基线测试: MrpackBuilder (DOWNLOAD/REFERENCE) 与 ZipBuilder"""

import json
import zipfile

import pytest

from modfetch.domain import ModLoader
from modfetch.adapters.packaging.mrpack_builder import MrpackBuilder
from modfetch.adapters.packaging.zip_builder import ZipBuilder

METADATA = {"name": "TestPack", "version": "1.0.0", "description": "test"}


def _make_source(base, files: dict[str, bytes]):
    for rel, content in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


class TestMrpackDownload:
    async def test_overrides_and_manifest(self, tmp_path):
        """DOWNLOAD 模式: 源目录内容进入 overrides，manifest.files 为空"""
        source = tmp_path / "source"
        _make_source(
            source,
            {
                "mods/sodium.jar": b"jar-a",
                "resourcepacks/pack.zip": b"zip-b",
            },
        )
        out = tmp_path / "out" / "pack"

        result = await MrpackBuilder().build(
            source_dir=str(source),
            output_path=str(out),
            metadata=METADATA,
            mc_version="1.21.1",
            mod_loader=ModLoader.FABRIC,
            loader_version="0.16.5",
        )

        assert result.endswith(".mrpack")
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "overrides/mods/sodium.jar" in names
            assert "overrides/resourcepacks/pack.zip" in names
            manifest = json.loads(zf.read("modrinth.index.json"))

        assert manifest["formatVersion"] == 1
        assert manifest["game"] == "minecraft"
        assert manifest["files"] == []
        assert manifest["dependencies"] == {
            "minecraft": "1.21.1",
            "fabric-loader": "0.16.5",
        }

    async def test_unknown_loader_version_omitted(self, tmp_path):
        """loader_version 为 None/unknown 时不出现在 dependencies"""
        source = tmp_path / "source"
        source.mkdir()
        out = tmp_path / "pack"

        result = await MrpackBuilder().build(
            source_dir=str(source),
            output_path=str(out),
            metadata=METADATA,
            mc_version="1.21.1",
            mod_loader=ModLoader.FORGE,
            loader_version=None,
        )
        with zipfile.ZipFile(result) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
        assert manifest["dependencies"] == {"minecraft": "1.21.1"}


class TestMrpackReference:
    async def test_files_written_to_manifest(self, tmp_path):
        """REFERENCE 模式: files 列表直接写入 manifest"""
        source = tmp_path / "empty"
        source.mkdir()
        out = tmp_path / "pack"

        files = [
            {
                "path": "mods/sodium.jar",
                "hashes": {"sha1": "a" * 40},
                "env": {"client": "required", "server": "required"},
                "downloads": ["https://cdn.modrinth.com/x/sodium.jar"],
                "fileSize": 100,
            }
        ]
        result = await MrpackBuilder().build(
            source_dir=str(source),
            output_path=str(out),
            metadata=METADATA,
            mc_version="1.21.1",
            mod_loader=ModLoader.FABRIC,
            files=files,
        )
        with zipfile.ZipFile(result) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
        assert manifest["files"] == files


class TestZip:
    async def test_archive_contents(self, tmp_path):
        source = tmp_path / "source"
        _make_source(source, {"mods/a.jar": b"a", "config/b.toml": b"b"})
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = await ZipBuilder().build(
            source_dir=str(source),
            output_path=str(out_dir),
            archive_name="pack",
        )

        assert result.endswith("pack.zip")
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "mods/a.jar" in names
            assert "config/b.toml" in names

    async def test_default_archive_name(self, tmp_path):
        """archive_name 缺省时使用源目录名"""
        source = tmp_path / "1.21.1-fabric"
        _make_source(source, {"mods/a.jar": b"a"})
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = await ZipBuilder().build(
            source_dir=str(source), output_path=str(out_dir)
        )
        assert "1.21.1-fabric.zip" in result
