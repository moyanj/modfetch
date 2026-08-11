"""Lock 文件服务单元测试

覆盖：
- LockFile to_dict / from_dict 往返一致性
- compute_fingerprint 同配置同指纹、改配置换指纹
- write_lock / read_lock 落盘与读取
- check_fingerprint 匹配 / 不匹配
- diff_locks 新增 / 移除 / 版本变更 / 无变化
- BuildLayout.lock_path_for 路径派生约定
- BuildPlan.from_dict 能正确还原 to_dict() 的输出（往返测试）
- LockError 在文件不存在 / JSON 非法 / 版本不兼容时抛出
"""

import json
from pathlib import Path

import pytest

from modfetch.application.build_layout import BuildLayout
from modfetch.application.lock_service import (
    LOCK_VERSION,
    LockDiff,
    LockFile,
    check_fingerprint,
    compute_fingerprint,
    diff_locks,
    read_lock,
    write_lock,
)
from modfetch.domain.build_plan import (
    ArtifactCategory,
    BuildPlan,
    BuildTarget,
    OutputSpec,
    ResolvedArtifact,
)
from modfetch.domain.config_models import ModFetchConfig, ModLoader
from modfetch.domain.errors import LockError

TARGET = BuildTarget("1.21.1", ModLoader.FABRIC)


def _artifact(pid: str = "AAAA0001", url: str = "https://ex.com/a.jar") -> ResolvedArtifact:
    """构造最小制品"""
    return ResolvedArtifact(
        project_id=pid,
        project_name=pid,
        category=ArtifactCategory.mods(),
        filename=f"{pid}.jar",
        url=url,
        hashes={"sha1": "0" * 40},
        destination=f"mods/{pid}.jar",
        target=TARGET,
    )


def _plan(artifacts=None) -> BuildPlan:
    return BuildPlan(
        targets=(TARGET,),
        artifacts=artifacts or (_artifact(),),
        outputs=(OutputSpec(format="mrpack", target=TARGET, output_name="pack"),),
        metadata={"name": "TestPack", "version": "1.0.0"},
    )


def _config(**overrides) -> ModFetchConfig:
    """构造最小配置（满足 from_dict 的必要字段）"""
    d = {
        "minecraft": {
            "version": ["1.21.1"],
            "mod_loader": "fabric",
            "mods": ["sodium"],
        },
        "output": {"download_dir": "/tmp/dl", "format": ["mrpack"]},
        "metadata": {"name": "TestPack", "version": "1.0.0"},
    }
    d.update(overrides)
    return ModFetchConfig.from_dict(d)


# ---------------------------------------------------------------------------
# BuildPlan.from_dict 往返一致性
# ---------------------------------------------------------------------------


class TestBuildPlanFromDict:
    def test_build_target_round_trip(self):
        """BuildTarget.to_dict → from_dict 还原一致"""
        t = BuildTarget("1.20.1", ModLoader.NEOFORGE)
        restored = BuildTarget.from_dict(t.to_dict())
        assert restored == t
        assert restored.loader == ModLoader.NEOFORGE

    def test_build_target_from_dict_invalid_loader(self):
        """无效 loader 值 → ValueError"""
        with pytest.raises(ValueError):
            BuildTarget.from_dict({"minecraft_version": "1.21", "loader": "未知"})

    def test_artifact_category_round_trip(self):
        for v in ("mods", "resourcepacks", "shaderpacks", "file"):
            c = ArtifactCategory.from_dict(v)
            assert c.to_dict() == v

    def test_resolved_artifact_round_trip(self):
        """ResolvedArtifact.to_dict → from_dict 还原一致（忽略 mrpack_entry）"""
        a = _artifact()
        d = a.to_dict()
        restored = ResolvedArtifact.from_dict(d)
        assert restored == a
        assert restored.hashes == a.hashes
        assert restored.environment == a.environment

    def test_output_spec_round_trip(self):
        o = OutputSpec(
            format="zip",
            target=TARGET,
            output_name="pack-1.0-mc1.21.1-fabric",
            mrpack_mode="reference",
        )
        restored = OutputSpec.from_dict(o.to_dict())
        assert restored == o
        assert restored.mrpack_mode == "reference"

    def test_plan_round_trip_full(self):
        """完整 BuildPlan 往返：targets / artifacts / outputs / metadata 一致"""
        plan = _plan()
        d = plan.to_dict()
        restored = BuildPlan.from_dict(d)
        assert restored == plan
        assert restored.targets == plan.targets
        assert restored.artifacts == plan.artifacts
        assert restored.outputs == plan.outputs
        assert restored.metadata == plan.metadata

    def test_plan_from_dict_empty(self):
        """空字段也安全"""
        plan = BuildPlan.from_dict({})
        assert plan.targets == ()
        assert plan.artifacts == ()
        assert plan.outputs == ()
        assert plan.metadata == {}


# ---------------------------------------------------------------------------
# LockFile to_dict / from_dict
# ---------------------------------------------------------------------------


class TestLockFile:
    def test_lockfile_round_trip(self):
        plan = _plan()
        lock = LockFile(
            lock_version=LOCK_VERSION,
            config_fingerprint="sha256:abc",
            config_path="mods.toml",
            features=("performance",),
            generated_at="2026-01-01T00:00:00+00:00",
            plan=plan,
        )
        d = lock.to_dict()
        restored = LockFile.from_dict(d)
        assert restored.lock_version == lock.lock_version
        assert restored.config_fingerprint == lock.config_fingerprint
        assert restored.config_path == lock.config_path
        assert restored.features == lock.features
        assert restored.generated_at == lock.generated_at
        assert restored.plan == lock.plan

    def test_lockfile_from_dict_missing_plan_raises(self):
        """plan 字段缺失 → LockError"""
        with pytest.raises(LockError):
            LockFile.from_dict({"config_fingerprint": "x", "lock_version": 1})


# ---------------------------------------------------------------------------
# compute_fingerprint
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_same_config_same_fingerprint(self):
        """同一配置两次计算指纹完全一致"""
        c = _config()
        fp1 = compute_fingerprint(c)
        fp2 = compute_fingerprint(c)
        assert fp1 == fp2
        assert fp1.startswith("sha256:")

    def test_different_config_different_fingerprint(self):
        """配置内容变化 → 指纹变化"""
        c1 = _config()
        c2 = _config(metadata={"name": "OtherPack", "version": "2.0"})
        assert compute_fingerprint(c1) != compute_fingerprint(c2)

    def test_features_change_fingerprint_changes(self):
        """features 被覆盖后指纹变化（because to_dict 含 features）"""
        c = _config()
        fp_before = compute_fingerprint(c)
        c.features = ["performance"]
        fp_after = compute_fingerprint(c)
        assert fp_before != fp_after


# ---------------------------------------------------------------------------
# write_lock / read_lock
# ---------------------------------------------------------------------------


class TestWriteReadLock:
    def test_write_creates_file_and_parents(self, tmp_path):
        """write_lock 创建文件并建立父目录"""
        plan = _plan()
        config = _config()
        lock_path = tmp_path / "nested" / "mods.lock.json"
        written = write_lock(lock_path, plan, config, "mods.toml")
        assert Path(written).exists()
        assert lock_path.exists()

    def test_write_then_read_round_trip(self, tmp_path):
        """写后读：指纹、features、plan 一致"""
        plan = _plan()
        config = _config()
        config.features = ["graphics"]
        lock_path = tmp_path / "mods.lock.json"
        write_lock(lock_path, plan, config, "mods.toml")

        restored = read_lock(lock_path)
        assert restored.config_fingerprint == compute_fingerprint(config)
        assert restored.features == ("graphics",)
        assert restored.plan == plan
        assert restored.config_path == "mods.toml"

    def test_lockjson_is_valid_json_with_expected_keys(self, tmp_path):
        """lock 文件内容是合法 JSON 且包含必要字段"""
        plan = _plan()
        config = _config()
        lock_path = tmp_path / "mods.lock.json"
        write_lock(lock_path, plan, config, "mods.toml")

        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["lock_version"] == LOCK_VERSION
        assert "config_fingerprint" in data
        assert "generated_at" in data
        assert "plan" in data
        assert "targets" in data["plan"]

    def test_read_lock_missing_file_raises(self, tmp_path):
        """文件不存在 → LockError"""
        with pytest.raises(LockError):
            read_lock(tmp_path / "nope.lock.json")

    def test_read_lock_invalid_json_raises(self, tmp_path):
        """非法 JSON → LockError"""
        p = tmp_path / "bad.lock.json"
        p.write_text("not json{", encoding="utf-8")
        with pytest.raises(LockError):
            read_lock(p)

    def test_read_lock_version_mismatch_raises(self, tmp_path):
        """lock_version 不兼容 → LockError"""
        p = tmp_path / "old.lock.json"
        p.write_text(
            json.dumps({"lock_version": 999, "config_fingerprint": "x"}),
            encoding="utf-8",
        )
        with pytest.raises(LockError):
            read_lock(p)


# ---------------------------------------------------------------------------
# check_fingerprint
# ---------------------------------------------------------------------------


class TestCheckFingerprint:
    def test_matching_fingerprint(self, tmp_path):
        plan = _plan()
        config = _config()
        lock_path = tmp_path / "x.lock.json"
        write_lock(lock_path, plan, config, "mods.toml")

        lock = read_lock(lock_path)
        assert check_fingerprint(lock, config) is True

    def test_mismatching_fingerprint(self, tmp_path):
        """配置改变后指纹不匹配"""
        plan = _plan()
        c1 = _config()
        lock_path = tmp_path / "x.lock.json"
        write_lock(lock_path, plan, c1, "mods.toml")

        # 改名后指纹变
        c2 = _config(metadata={"name": "Changed", "version": "1.0"})
        lock = read_lock(lock_path)
        assert check_fingerprint(lock, c2) is False


# ---------------------------------------------------------------------------
# diff_locks
# ---------------------------------------------------------------------------


def _lockfile(artifacts):
    """构造含给定制品的 LockFile（指纹/时间戳无关紧要）"""
    return LockFile(
        lock_version=LOCK_VERSION,
        config_fingerprint="x",
        config_path="",
        features=(),
        generated_at="",
        plan=_plan(artifacts=artifacts),
    )


class TestDiffLocks:
    def test_no_changes(self):
        a = _artifact()
        old = _lockfile((a,))
        new = _lockfile((a,))
        diff = diff_locks(old, new)
        assert diff == LockDiff(added=(), removed=(), changed=())

    def test_added(self):
        a = _artifact("A")
        b = _artifact("B")
        old = _lockfile((a,))
        new = _lockfile((a, b))
        diff = diff_locks(old, new)
        assert diff.added == ("B",)
        assert diff.removed == ()
        assert diff.changed == ()

    def test_removed(self):
        a = _artifact("A")
        b = _artifact("B")
        old = _lockfile((a, b))
        new = _lockfile((a,))
        diff = diff_locks(old, new)
        assert diff.added == ()
        assert diff.removed == ("B",)
        assert diff.changed == ()

    def test_changed_url(self):
        a_old = _artifact("A", url="https://old/a.jar")
        a_new = _artifact("A", url="https://new/a.jar")
        old = _lockfile((a_old,))
        new = _lockfile((a_new,))
        diff = diff_locks(old, new)
        assert diff.added == ()
        assert diff.removed == ()
        assert len(diff.changed) == 1
        pid, old_url, new_url = diff.changed[0]
        assert pid == "A"
        assert old_url == "https://old/a.jar"
        assert new_url == "https://new/a.jar"


# ---------------------------------------------------------------------------
# BuildLayout.lock_path_for
# ---------------------------------------------------------------------------


class TestLockPathFor:
    def test_lock_path_beside_config(self, tmp_path):
        """lock 文件与配置同目录，文件名 = stem + .lock.json"""
        layout = BuildLayout(tmp_path / "downloads")
        cfg = tmp_path / "mods.toml"
        lock = layout.lock_path_for(cfg)
        assert lock == tmp_path / "mods.lock.json"
        assert lock.parent == tmp_path
        assert lock.name == "mods.lock.json"

    def test_lock_path_for_nondefault_config_name(self, tmp_path):
        """非 mods.toml 的配置文件名同样遵守约定"""
        layout = BuildLayout(tmp_path / "dl")
        cfg = tmp_path / "sub" / "my-pack.yaml"
        lock = layout.lock_path_for(cfg)
        assert lock.name == "my-pack.lock.json"
        assert lock.parent == tmp_path / "sub"

    def test_lock_path_independent_of_download_dir(self, tmp_path):
        """lock 路径不依赖 download_dir（位于配置同目录）"""
        layout_a = BuildLayout(tmp_path / "downloads_a")
        layout_b = BuildLayout(tmp_path / "downloads_b")
        cfg = tmp_path / "mods.toml"
        assert layout_a.lock_path_for(cfg) == layout_b.lock_path_for(cfg)
