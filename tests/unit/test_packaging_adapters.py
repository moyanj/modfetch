"""打包适配器单元测试: MrpackPackager / ZipPackager / PackagerDispatcher"""

import json
import zipfile
from pathlib import Path

import pytest

from modfetch.adapters.packaging import (
    MrpackPackager,
    PackagerDispatcher,
    ZipPackager,
)
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import ModLoader
from modfetch.domain.errors import PackagerError

TARGET = BuildTarget(minecraft_version="1.21.1", loader=ModLoader.FABRIC)


def _artifact(
    filename: str,
    category: str = "mods",
    origin: str = "catalog",
    url: str = "https://cdn.modrinth.com/x/f.jar",
) -> ResolvedArtifact:
    cat = ArtifactCategory(category)
    return ResolvedArtifact(
        project_id=f"id-{filename}",
        project_name=filename,
        category=cat,
        filename=filename,
        url=url,
        hashes={"sha1": "a" * 40},
        destination=(
            filename if category == "file" else f"{category}/{filename}"
        ),
        target=TARGET,
        size=100,
        origin=origin,
    )


def _plan(artifacts=(), outputs=()) -> BuildPlan:
    return BuildPlan(targets=(TARGET,), artifacts=artifacts, outputs=outputs)


def _seed_workspace(workspace: Path, files: dict[str, bytes]) -> None:
    for rel, content in files.items():
        path = workspace / TARGET.dir_name / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


class TestMrpackPackager:
    async def test_download_mode(self, tmp_path):
        """DOWNLOAD 模式: workspace 内容进入 overrides"""
        _seed_workspace(tmp_path, {"mods/a.jar": b"a"})
        packager = MrpackPackager(metadata={"name": "P", "version": "1.0.0"})
        spec = OutputSpec(
            format="mrpack", target=TARGET,
            output_name="pack", mrpack_mode="download",
        )

        artifact = await packager.package(_plan(), spec, TARGET, tmp_path)

        assert artifact.format == "mrpack"
        assert artifact.target == TARGET
        assert artifact.size > 0
        with zipfile.ZipFile(artifact.path) as zf:
            assert "overrides/mods/a.jar" in zf.namelist()
            manifest = json.loads(zf.read("modrinth.index.json"))
            assert manifest["name"] == "P"

    async def test_reference_mode_files_from_plan(self, tmp_path):
        """REFERENCE 模式: manifest.files 来自 plan 制品而非实例状态"""
        _seed_workspace(tmp_path, {"mods/a.jar": b"a"})
        packager = MrpackPackager(metadata={"name": "P", "version": "1.0.0"})
        spec = OutputSpec(
            format="mrpack", target=TARGET,
            output_name="pack", mrpack_mode="reference",
        )
        plan = _plan(artifacts=[_artifact("a.jar"), _artifact("b.jar")])

        artifact = await packager.package(plan, spec, TARGET, tmp_path)

        with zipfile.ZipFile(artifact.path) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
            paths = {f["path"] for f in manifest["files"]}
            assert paths == {"mods/a.jar", "mods/b.jar"}
            assert manifest["files"][0]["fileSize"] == 100
            # 平台解析的制品不进入 overrides
            assert not any(
                n.startswith("overrides/mods/") for n in zf.namelist()
            )

    async def test_reference_mode_extra_urls_in_overrides(self, tmp_path):
        """REFERENCE 模式: extra_urls 文件仍进入 overrides"""
        _seed_workspace(tmp_path, {"config.toml": b"[x]"})
        packager = MrpackPackager(metadata={"name": "P", "version": "1.0.0"})
        spec = OutputSpec(
            format="mrpack", target=TARGET,
            output_name="pack", mrpack_mode="reference",
        )
        plan = _plan(artifacts=[
            _artifact("a.jar"),
            _artifact("config.toml", category="file", origin="extra_url",
                      url="file:///x/config.toml"),
        ])

        artifact = await packager.package(plan, spec, TARGET, tmp_path)

        with zipfile.ZipFile(artifact.path) as zf:
            assert "overrides/config.toml" in zf.namelist()
            manifest = json.loads(zf.read("modrinth.index.json"))
            # extra_urls 不写入 manifest.files（沿用旧契约）
            assert {f["path"] for f in manifest["files"]} == {"mods/a.jar"}

    async def test_loader_version_resolved(self, tmp_path):
        """加载器版本通过 resolver 注入 manifest"""
        _seed_workspace(tmp_path, {})

        async def resolver(loader, mc_version):
            assert loader == ModLoader.FABRIC
            assert mc_version == "1.21.1"
            return "0.16.5"

        packager = MrpackPackager(
            loader_version_resolver=resolver,
            metadata={"name": "P", "version": "1.0.0"},
        )
        spec = OutputSpec(
            format="mrpack", target=TARGET,
            output_name="pack", mrpack_mode="download",
        )
        artifact = await packager.package(_plan(), spec, TARGET, tmp_path)

        with zipfile.ZipFile(artifact.path) as zf:
            manifest = json.loads(zf.read("modrinth.index.json"))
            assert manifest["dependencies"]["fabric-loader"] == "0.16.5"


class TestZipPackager:
    async def test_zip_output(self, tmp_path):
        _seed_workspace(tmp_path, {"mods/a.jar": b"a"})
        packager = ZipPackager()
        spec = OutputSpec(format="zip", target=TARGET, output_name="archive")

        artifact = await packager.package(_plan(), spec, TARGET, tmp_path)

        assert artifact.format == "zip"
        assert artifact.size > 0
        with zipfile.ZipFile(artifact.path) as zf:
            assert "mods/a.jar" in zf.namelist()

    async def test_missing_source_raises(self, tmp_path):
        """源目录不存在 → PackagerError（不再静默跳过）"""
        packager = ZipPackager()
        spec = OutputSpec(format="zip", target=TARGET, output_name="archive")

        with pytest.raises(PackagerError):
            await packager.package(_plan(), spec, TARGET, tmp_path)


class TestDispatcher:
    async def test_routes_by_format(self, tmp_path):
        _seed_workspace(tmp_path, {"mods/a.jar": b"a"})
        dispatcher = PackagerDispatcher({
            "mrpack": MrpackPackager(metadata={"name": "P", "version": "1"}),
            "zip": ZipPackager(),
        })

        mrpack = await dispatcher.package(
            _plan(),
            OutputSpec(format="mrpack", target=TARGET, output_name="p"),
            TARGET, tmp_path,
        )
        zip_out = await dispatcher.package(
            _plan(),
            OutputSpec(format="zip", target=TARGET, output_name="z"),
            TARGET, tmp_path,
        )

        assert mrpack.path.endswith(".mrpack")
        assert zip_out.path.endswith(".zip")

    async def test_unregistered_format_raises(self, tmp_path):
        dispatcher = PackagerDispatcher({})
        with pytest.raises(PackagerError, match="未注册"):
            await dispatcher.package(
                _plan(),
                OutputSpec(format="7z", target=TARGET, output_name="x"),
                TARGET, tmp_path,
            )
