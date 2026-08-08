"""构建布局与物化测试（新目录结构）"""

import json
import os
import shutil
from pathlib import Path

import pytest

from modfetch.adapters.packaging.atomicio import AtomicWriteError, write_atomic
from modfetch.application.build_layout import (
    BuildLayout,
    LayoutError,
    clean_layout,
    normalize_slug,
    probe_hardlink_support,
)
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import ModLoader

TARGET = BuildTarget(minecraft_version="1.21.1", loader=ModLoader.FABRIC)


def _artifact(filename: str, category: str = "mods",
              hashes: dict | None = None, url: str = "https://x/f.jar") -> ResolvedArtifact:
    cat = ArtifactCategory(category)
    return ResolvedArtifact(
        project_id=f"id-{filename}",
        project_name=filename,
        category=cat,
        filename=filename,
        url=url,
        hashes=hashes if hashes is not None else {"sha1": "a" * 40},
        destination=filename if category == "file" else f"{category}/{filename}",
        target=TARGET,
        size=1,
    )


class TestNormalizeSlug:
    def test_basic_lowercase(self):
        assert normalize_slug("My Awesome Pack") == "my-awesome-pack"

    def test_ascii_whitelist(self):
        """仅保留 ASCII 字母数字 - _；中文/符号剔除"""
        assert normalize_slug("Pack_中文-1.0!") == "pack_-10"

    def test_trim_dashes(self):
        assert normalize_slug("---Pack---") == "pack"

    def test_empty_raises(self):
        with pytest.raises(LayoutError):
            normalize_slug("!!!###")


class TestBuildLayout:
    def test_directories(self, tmp_path):
        layout = BuildLayout(tmp_path / "dl")
        assert layout.root == (tmp_path / "dl").resolve()
        assert layout.build_dir == layout.root / "build"
        assert layout.cache_dir == layout.root / "build" / "cache"
        assert layout.dist_dir == layout.root / "dist"

    def test_cache_key_sha1_priority(self, tmp_path):
        """有 sha1 → 内容寻址；无 sha1 → URL 摘要"""
        layout = BuildLayout(tmp_path)
        art = _artifact("a.jar", hashes={"sha1": "ab" * 20})
        sha1_path = layout.cache_path_for(art)
        assert sha1_path.name == "ab" * 20
        assert sha1_path.parent.name == "ab"  # 2 位分片
        assert sha1_path.parent.parent.name == "sha1"

        url_art = _artifact("b.jar", hashes={}, url="https://cdn/x/b.jar")
        url_path = layout.cache_path_for(url_art)
        assert url_path.parent.name == "url"
        assert url_path.suffix == ""  # blob 无扩展名（digest 命名）

    def test_url_meta_path(self, tmp_path):
        layout = BuildLayout(tmp_path)
        meta = layout.url_meta("https://x/b.jar")
        assert meta.name.endswith(".meta.json")
        assert meta.parent.name == "url"

    def test_workspace_for_blocks_traversal(self, tmp_path):
        layout = BuildLayout(tmp_path)
        with pytest.raises(LayoutError):
            layout.workspace_for(TARGET, "../evil.jar")
        with pytest.raises(LayoutError):
            layout.workspace_for(TARGET, "/abs.jar")

    def test_output_path(self, tmp_path):
        layout = BuildLayout(tmp_path)
        spec = OutputSpec(format="mrpack", target=TARGET,
                          output_name="testpack-1.0.0-mc1.21.1-fabric")
        assert layout.output_path(spec) == (
            layout.dist_dir / "testpack-1.0.0-mc1.21.1-fabric.mrpack"
        )


class TestProbeHardlink:
    def test_probe_ok(self, tmp_path):
        layout = BuildLayout(tmp_path)
        probe_hardlink_support(layout)  # 不应抛异常
        # 探测文件已清理
        assert not (layout.cache_dir / ".hardlink-probe").exists()

    def test_probe_fails_on_unsupported(self, tmp_path, monkeypatch):
        """文件系统不支持硬链接 → LayoutError"""
        layout = BuildLayout(tmp_path)
        real_link = os.link

        def fake_link(src, dst):
            raise OSError("Operation not permitted")

        monkeypatch.setattr(os, "link", fake_link)
        with pytest.raises(LayoutError, match="硬链接"):
            probe_hardlink_support(layout)


class TestCleanLayout:
    def test_clean_workspaces_keep_cache(self, tmp_path):
        layout = BuildLayout(tmp_path)
        (layout.target_build_dir(TARGET) / "mods").mkdir(parents=True)
        (layout.cache_dir / "sha1").mkdir(parents=True)
        removed = clean_layout(layout, cache=False)
        assert layout.target_build_dir(TARGET).parent.exists()
        assert not layout.target_build_dir(TARGET).exists()
        assert layout.cache_dir.exists()  # cache 保留

    def test_clean_cache_flag(self, tmp_path):
        layout = BuildLayout(tmp_path)
        (layout.cache_dir / "sha1").mkdir(parents=True)
        removed = clean_layout(layout, cache=True)
        assert not layout.cache_dir.exists()


class TestAtomicWrite:
    def test_write_atomic(self, tmp_path):
        target = tmp_path / "out.mrpack"
        write_atomic(target, lambda t: t.write_bytes(b"data"))
        assert target.read_bytes() == b"data"

    def test_no_tmp_leftover(self, tmp_path):
        target = tmp_path / "out.zip"
        write_atomic(target, lambda t: t.write_bytes(b"x"))
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
        assert leftovers == []

    def test_writer_failure_no_target(self, tmp_path):
        target = tmp_path / "out.mrpack"

        def boom(t):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            write_atomic(target, boom)
        assert not target.exists()

    def test_replace_retry_on_permission(self, tmp_path, monkeypatch):
        """Windows PermissionError → 退避重试后成功"""
        target = tmp_path / "out.zip"
        target.write_bytes(b"old")
        calls = {"n": 0}
        real_replace = os.replace

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("locked by AV")
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", flaky_replace)
        write_atomic(target, lambda t: t.write_bytes(b"new"))
        assert target.read_bytes() == b"new"
        assert calls["n"] == 2

    def test_replace_exhausted(self, tmp_path, monkeypatch):
        """始终 PermissionError → AtomicWriteError"""
        target = tmp_path / "out.zip"

        def always_fail(src, dst):
            raise PermissionError("locked")

        monkeypatch.setattr(os, "replace", always_fail)
        with pytest.raises(AtomicWriteError):
            write_atomic(target, lambda t: t.write_bytes(b"x"))
