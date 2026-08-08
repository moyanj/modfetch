"""ExecuteBuild 新布局物化测试: cache → 工作区硬链接/复制"""

import os
import shutil
from pathlib import Path

import pytest

from modfetch.application.build_layout import BuildLayout
from modfetch.application.execute_build import BuildOptions, ExecuteBuild
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import ModLoader
from modfetch.ports.downloader import DownloadResult, DownloadTask

TARGET = BuildTarget(minecraft_version="1.21.1", loader=ModLoader.FABRIC)


class _RecordingDownloader:
    """记录下载调用的桩 downloader（把假文件写到 cache 目标路径）"""

    def __init__(self, content: bytes):
        self.content = content
        self.calls: list[DownloadTask] = []
        self.results: list[DownloadResult] = []

    async def download(self, task: DownloadTask, progress=None) -> DownloadResult:
        self.calls.append(task)
        path = Path(task.destination) / task.filename
        # 模拟真实下载器的缓存幂等：目标已存在 → 跳过（不再写入）
        if path.exists():
            result = DownloadResult(
                success=True, filename=task.filename, path=str(path),
                bytes_downloaded=0, skipped=True,
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.content)
            result = DownloadResult(
                success=True, filename=task.filename, path=str(path),
                bytes_downloaded=len(self.content),
            )
        self.results.append(result)
        return result

    async def close(self):
        pass


class _NoopSink:
    async def publish(self, event):
        pass

    async def close(self):
        pass


class _FailingDownloader:
    """下载失败桩：全部任务返回 success=False 且不写文件"""

    def __init__(self, error: str = "网络错误"):
        self.error = error
        self.calls: list[DownloadTask] = []

    async def download(self, task: DownloadTask, progress=None) -> DownloadResult:
        self.calls.append(task)
        return DownloadResult(
            success=False, filename=task.filename,
            error=self.error, error_code="E301",
        )

    async def close(self):
        pass


def _plan(artifacts, outputs) -> BuildPlan:
    return BuildPlan(
        targets=(TARGET,), artifacts=tuple(artifacts), outputs=tuple(outputs)
    )


def _artifact(filename: str, hashes: dict | None = None) -> ResolvedArtifact:
    return ResolvedArtifact(
        project_id=f"id-{filename}",
        project_name=filename,
        category=ArtifactCategory.mods(),
        filename=filename,
        url=f"https://cdn/x/{filename}",
        hashes=hashes if hashes is not None else {"sha1": "b" * 40},
        destination=f"mods/{filename}",
        target=TARGET,
        size=1,
    )


@pytest.mark.parametrize("link_mode", ["link", "copy"])
async def test_materialize_link_and_copy(tmp_path, link_mode):
    """物化后工作区出现 mods/<file>，内容一致"""
    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _RecordingDownloader(b"jar-content")
    packager = _NoopPackager()

    exec_ = ExecuteBuild(downloader, packager)
    result = await exec_.execute(
        plan, "job", _NoopSink(),
        BuildOptions(layout=layout, link_mode=link_mode),
    )

    assert result.success
    dest = layout.workspace_for(TARGET, "mods/a.jar")
    assert dest.exists()
    assert dest.read_bytes() == b"jar-content"

    # cache 中有 blob，工作区文件存在
    cache_blob = layout.cache_path_for(artifacts[0])
    assert cache_blob.exists()


class _NoopPackager:
    async def package(self, plan, spec, source_dir: Path, output_path: Path):
        # 模拟打包器：把 source_dir 内容写进 output_path（真实语义）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_name(output_path.name + ".tmp")
        shutil.make_archive(str(tmp), "zip", source_dir)
        os.replace(str(tmp) + ".zip", output_path)
        return type("A", (), {
            "path": str(output_path), "format": spec.format,
            "target": spec.target, "size": 1,
        })()


async def test_materialize_reuses_cache(tmp_path):
    """同一制品两次构建：第二次不重复下载（缓存命中跳过）"""
    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _RecordingDownloader(b"jar-content")

    exec_ = ExecuteBuild(downloader, _NoopPackager())
    await exec_.execute(plan, "job1", _NoopSink(), BuildOptions(layout=layout))
    assert downloader.results[0].skipped is False  # 首次真下载

    # 第二次构建：cache 已命中 → 下载跳过（结果 skipped=True）
    await exec_.execute(plan, "job2", _NoopSink(), BuildOptions(layout=layout))
    assert downloader.results[-1].skipped is True
    # 工作区仍正确物化
    assert (layout.workspace_for(TARGET, "mods/a.jar")).exists()


async def test_workspace_rebuilt_clean(tmp_path):
    """工作区每次重建：旧文件被清空"""
    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _RecordingDownloader(b"content")

    exec_ = ExecuteBuild(downloader, _NoopPackager())
    await exec_.execute(plan, "job", _NoopSink(), BuildOptions(layout=layout))

    # 手动塞入过期文件（模拟上次构建残留）
    stale = layout.workspace_for(TARGET, "mods/stale.jar")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"stale")

    await exec_.execute(plan, "job2", _NoopSink(), BuildOptions(layout=layout))
    assert not stale.exists()
    assert (layout.workspace_for(TARGET, "mods/a.jar")).exists()


async def test_dist_output_path(tmp_path):
    """产物落在 dist/ 下（扁平）"""
    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _RecordingDownloader(b"content")

    exec_ = ExecuteBuild(downloader, _NoopPackager())
    result = await exec_.execute(plan, "job", _NoopSink(), BuildOptions(layout=layout))

    assert result.success
    out = layout.output_path(spec)
    assert out.parent == layout.dist_dir
    assert (layout.dist_dir / "pack.zip").exists()


async def test_materialize_failure_recorded(tmp_path, monkeypatch):
    """硬链接失败 → BuildError（phase=materialize）而非静默复制"""
    import modfetch.application.execute_build as eb

    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _RecordingDownloader(b"content")

    async def fail_link(src, dst):
        raise eb.LayoutError("硬链接失败: 测试模拟 (Operation not permitted)")

    monkeypatch.setattr(eb, "_link_artifact", fail_link)
    exec_ = ExecuteBuild(downloader, _NoopPackager())
    result = await exec_.execute(plan, "job", _NoopSink(), BuildOptions(layout=layout))

    materialize_errors = [e for e in result.errors if e.phase == "materialize"]
    assert materialize_errors, "应记录物化错误"
    assert "硬链接失败" in materialize_errors[0].message


async def test_download_failure_skips_materialize(tmp_path):
    """下载失败 → 物化跳过：仅 E300 下载错误，不重复报 E400"""
    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _FailingDownloader("下载失败: 网络错误")
    packager = _NoopPackager()

    exec_ = ExecuteBuild(downloader, packager)
    result = await exec_.execute(
        plan, "job", _NoopSink(), BuildOptions(layout=layout)
    )

    # 下载失败记为 E300（phase=download），且不产生误导性物化错误
    download_errors = [e for e in result.errors if e.phase == "download"]
    materialize_errors = [e for e in result.errors if e.phase == "materialize"]
    assert len(download_errors) == 1
    assert download_errors[0].code == "E301"
    assert materialize_errors == [], "下载失败不应再报物化错误"
    # 工作区不出现失败制品的残影
    assert not layout.workspace_for(TARGET, "mods/a.jar").exists()


class _RecordingPackager:
    """记录 package 调用次数的桩打包器（验证失败时不应被调用）"""

    def __init__(self, source_dir: Path):
        self.package_calls = 0
        self._source_dir = source_dir

    async def package(self, plan, spec, source_dir: Path, output_path: Path):
        self.package_calls += 1
        # 物化失败的 target 工作区为空/缺失，不应到达打包
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"artifact")
        return type("A", (), {
            "path": str(output_path), "format": spec.format,
            "target": spec.target, "size": 1,
        })()


async def test_download_failure_skips_packaging(tmp_path):
    """下载失败 → 跳过该 target 的打包：不产出残缺产物，outputs 不含失败路径"""
    artifacts = [_artifact("a.jar")]
    spec = OutputSpec(format="zip", target=TARGET, output_name="pack")
    plan = _plan(artifacts, [spec])
    layout = BuildLayout(tmp_path / "dl")
    downloader = _FailingDownloader("下载失败: 校验失败")
    packager = _RecordingPackager(layout.target_build_dir(TARGET))

    exec_ = ExecuteBuild(downloader, packager)
    result = await exec_.execute(
        plan, "job", _NoopSink(), BuildOptions(layout=layout)
    )

    # 下载失败已记录错误，但打包必须被跳过
    assert [e for e in result.errors if e.phase == "download"]
    assert packager.package_calls == 0, "下载失败不应触发打包"
    assert result.outputs == (), "下载失败时 outputs 不应包含产物路径"
    assert not layout.output_path(spec).exists(), "dist 不应留下残缺产物"
