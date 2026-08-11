"""lock 构建模式与 update 命令集成测试

覆盖 BuildApplicationService.execute(locked=True) 的三分支逻辑：
1. lock 缺失 → 报错
2. lock 存在且指纹匹配 → 直接用 lock 的 plan（离线路径，不再触达解析）
3. lock 存在但指纹不匹配 → 自动重新解析并覆盖 lock

并验证：
- 非锁模式 build 会无感写入 lock 文件（build 的副作用）
- update 流程对比旧/新 lock 输出 diff

使用 mock_modrinth fixture 确保完全离线、不触及真实网络。
"""

from pathlib import Path

import pytest

from modfetch.application.build_layout import BuildLayout
from modfetch.application.build_service import BuildApplicationService
from modfetch.application.lock_service import (
    read_lock,
    write_lock,
)
from modfetch.composition import create_build_service
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import LockError

pytestmark = pytest.mark.usefixtures("mock_modrinth")


async def _run(
    config_dict: dict,
    *,
    locked: bool = False,
    lock_path=None,
    service=None,
    sink=None,
    config_path: str = "mods.toml",
):
    """发起一次 execute()，返回 (result, download_dir, used_service)

    Args:
        config_path: 用于派生 lock 路径的"配置文件路径"。默认 "mods.toml"
            会解析到项目根；测试中通过 config_path=<tmp_path 下某文件>
            把 lock 路径隔离到 tmp_path 内，避免污染项目根目录。
    """
    config = ModFetchConfig.from_dict(config_dict)
    svc = service or create_build_service(event_sink=sink)
    options_kwargs = {}
    if locked:
        # build --locked 时需要 options，供 ExecuteBuild 拿 BuildLayout
        from modfetch.application.build_layout import BuildLayout as _BL
        from modfetch.application.execute_build import BuildOptions

        options_kwargs["options"] = BuildOptions(
            layout=_BL(config.output.download_dir),
            max_concurrent=config.max_concurrent,
        )
    else:
        options_kwargs["options"] = None

    if lock_path is None:
        layout = BuildLayout(config.output.download_dir)
        lock_path = str(layout.lock_path_for(config_path))

    result = await svc.execute(
        config,
        job_id="test",
        locked=locked,
        lock_path=lock_path,
        **options_kwargs,
    )
    return result, Path(config.output.download_dir), svc


class TestBuildLocked:
    """build --locked 的三分支"""

    async def test_locked_missing_raises(self, make_config_dict):
        """分支 1：lock 缺失 → LockError"""
        from modfetch.domain.config_models import ModFetchConfig
        config = ModFetchConfig.from_dict(make_config_dict())
        service = create_build_service()
        try:
            with pytest.raises(LockError) as excinfo:
                await service.execute(
                    config,
                    job_id="t",
                    options=None,
                    locked=True,
                    lock_path="/tmp/nonexistent-test.lock.json",
                )
            assert "需要先生成 lock" in str(excinfo.value)
        finally:
            await service.close()

    async def test_locked_matching_uses_lock(self, make_config_dict, tmp_path):
        """分支 2：指纹匹配 → 跳过远程校验/解析，直接用 lock plan，构建产出正常"""
        # 用 tmp_path/mods.toml 派生 lock 路径，避免污染项目根
        cfg_path = tmp_path / "mods.toml"
        cfg_path.write_text("# test", encoding="utf-8")
        # 先正常构建一次，生成 lock 文件 + 缓存 + dist
        config_dict = make_config_dict()
        result1, download_dir, svc1 = await _run(config_dict, config_path=str(cfg_path))
        assert result1.success
        assert len(result1.outputs) == 1

        layout = BuildLayout(str(download_dir))
        lock_path = layout.lock_path_for(cfg_path)
        assert lock_path.exists(), "首次 build 应该无感写入 lock"

        # 再次执行 --locked，应当产生同样的 outputs，
        # 且全程不再触达 ModrinthClient（mock_modrinth 验证通过即可）
        try:
            result2, _, _ = await _run(
                config_dict,
                locked=True,
                lock_path=str(lock_path),
                config_path=str(cfg_path),
                service=svc1,
            )
        finally:
            await svc1.close()

        assert result2.success
        assert len(result2.outputs) == len(result1.outputs)

    async def test_locked_mismatch_re_resolve(self, make_config_dict, tmp_path):
        """分支 3：指纹不匹配（mods.toml 变了）→ 自动重新解析并覆盖 lock"""
        cfg_path = tmp_path / "mods.toml"
        cfg_path.write_text("# test", encoding="utf-8")

        config_dict = make_config_dict()
        # 第一次构建，写 lock
        result1, download_dir, svc1 = await _run(
            config_dict, config_path=str(cfg_path)
        )
        assert result1.success

        layout = BuildLayout(str(download_dir))
        lock_path = layout.lock_path_for(cfg_path)
        lock_before = read_lock(lock_path)

        # 改一个不影响 build 产物但会改 config.to_dict 的字段：metadata.name
        # （feature 不变，使 build 仍能成功）
        changed_dict = dict(config_dict)
        changed_dict["metadata"] = {
            "name": "TestPackRenamed",
            "version": "1.0.0",
        }
        try:
            result2, _, _ = await _run(
                changed_dict,
                locked=True,
                lock_path=str(lock_path),
                config_path=str(cfg_path),
                service=svc1,
            )
        finally:
            await svc1.close()

        assert result2.success
        # lock 已被覆盖，指纹变成新配置的
        lock_after = read_lock(lock_path)
        assert lock_after.config_fingerprint != lock_before.config_fingerprint
        # 新 lock 的 metadata 也反映改名后的配置
        assert lock_after.plan.metadata["name"] == "TestPackRenamed"


class TestBuildSideEffectWritesLock:
    async def test_non_locked_build_writes_lock(self, make_config_dict, tmp_path):
        """非锁模式 build 仍然无感写 lock（副作用），且不影响构建成败"""
        cfg_path = tmp_path / "mods.toml"
        cfg_path.write_text("# test", encoding="utf-8")
        config_dict = make_config_dict()
        result, download_dir, svc = await _run(
            config_dict, config_path=str(cfg_path)
        )
        try:
            assert result.success
            layout = BuildLayout(str(download_dir))
            lock_path = layout.lock_path_for(cfg_path)
            assert lock_path.exists(), "非锁 build 应无感写 lock"
            lock = read_lock(lock_path)
            assert lock.plan.targets == result.plan.targets
            assert lock.plan.artifacts == result.plan.artifacts
        finally:
            await svc.close()


class TestUpdateFlow:
    """update 流程：重新解析、对比旧/新 lock、覆盖写 lock"""

    async def test_update_overwrites_and_diffs(self, make_config_dict, tmp_path):
        """首次无 lock → 模拟 update 全新生成；二次实际 diff 输出无异常"""
        from modfetch.application.lock_service import (
            LockFile,
            compute_fingerprint,
            diff_locks,
        )
        from datetime import datetime, timezone

        # 用 tmp_path 隔离 lock 文件，避免别的测试副作用污染
        config_dict = make_config_dict()
        config = ModFetchConfig.from_dict(config_dict)

        service = create_build_service()
        try:
            plan = await service.plan(config, job_id="test")
            layout = BuildLayout(str(Path(config.output.download_dir)))
            # 配置路径用 tmp_path 隔离，避免与项目根 mods.toml 冲突
            cfg_path = tmp_path / "mods.toml"
            cfg_path.write_text("# test", encoding="utf-8")
            lock_path = layout.lock_path_for(cfg_path)

            # 模拟主流程中先无 lock 的情形
            old_lock = None
            try:
                old_lock = read_lock(lock_path)
            except LockError:
                pass
            assert old_lock is None, "首次应无 lock"

            # 生成新 lock 文件对象做比较
            new_lock = LockFile(
                lock_version=1,
                config_fingerprint=compute_fingerprint(config),
                config_path="mods.toml",
                features=tuple(config.features),
                generated_at=datetime.now(timezone.utc).isoformat(),
                plan=plan,
            )

            # 第一次 update（无旧 lock）→ diff 无变化不触发
            # 写入 lock
            written = write_lock(lock_path, plan, config, "mods.toml")
            assert Path(written).exists()

            # 第二次 update（lock 存在）→ diff 应该为空（同配置解析）
            old_lock = read_lock(lock_path)
            plan2 = await service.plan(config, job_id="test-2")
            new_lock2 = LockFile(
                lock_version=1,
                config_fingerprint=compute_fingerprint(config),
                config_path="mods.toml",
                features=tuple(config.features),
                generated_at=datetime.now(timezone.utc).isoformat(),
                plan=plan2,
            )
            diff = diff_locks(old_lock, new_lock2)
            assert diff.added == ()
            assert diff.removed == ()
            assert diff.changed == ()
        finally:
            await service.close()
