"""JobApplicationService 端到端测试（Web 作业路径）"""

import pytest

from modfetch.adapters.jobs import JobApplicationService

pytestmark = pytest.mark.usefixtures("mock_modrinth")


async def _wait_job(manager, job):
    """等待后台任务结束"""
    if job._task is not None:
        await job._task


class TestJobLifecycle:
    async def test_create_start_complete(self, make_config_dict):
        """创建 → 启动 → 完成，结果来自 BuildResult 而非 FS 扫描"""
        manager = JobApplicationService()
        job_id = manager.create_job(make_config_dict())
        manager.start_job(job_id)

        job = manager.get_job(job_id)
        await _wait_job(manager, job)

        assert job.status == "completed"
        assert job.completed_at is not None
        assert len(job.results) == 1
        result = job.results[0]
        assert result.filename.endswith(".mrpack")
        assert result.mc_version == "1.21.1"
        assert result.loader == "fabric"
        assert result.size > 0

    async def test_event_stream_replay(self, make_config_dict):
        """事件流: 晚订阅者可回放完整历史"""
        manager = JobApplicationService()
        job_id = manager.create_job(make_config_dict())
        manager.start_job(job_id)
        await _wait_job(manager, manager.get_job(job_id))

        events = [e async for e in manager.subscribe(job_id)]
        names = [e["event"] for e in events]

        assert names[0] == "job_started"
        assert "phase_change" in names
        assert "stats_update" in names
        assert "resolve_complete" in names
        assert "download_complete" in names
        assert "package_complete" in names
        assert names[-1] == "job_complete"

        # job_started 携带配置摘要（前端契约）
        assert events[0]["data"]["config_summary"]["mod_count"] == 1

    async def test_failed_job(self, make_config_dict):
        """下载失败 → 任务 failed，错误结构化"""
        manager = JobApplicationService()
        job_id = manager.create_job(
            make_config_dict(
                minecraft={
                    "extra_urls": [{"url": "file:///nonexistent/ghost.jar"}]
                }
            )
        )
        manager.start_job(job_id)
        job = manager.get_job(job_id)
        await _wait_job(manager, job)

        assert job.status == "failed"
        assert len(job.errors) >= 1
        assert job.errors[0].code == "E300"

        events = [e async for e in manager.subscribe(job_id)]
        assert events[-1]["event"] == "job_failed"

    async def test_invalid_config_job_fails(self):
        """配置解析失败 → 任务 failed（E101）"""
        manager = JobApplicationService()
        job_id = manager.create_job({"minecraft": {"mods": ["sodium"]}})
        manager.start_job(job_id)
        job = manager.get_job(job_id)
        await _wait_job(manager, job)

        assert job.status == "failed"
        assert job.errors[0].code == "E101"

    async def test_start_non_pending_raises(self, make_config_dict):
        """重复启动 → ValueError"""
        manager = JobApplicationService()
        job_id = manager.create_job(make_config_dict())
        manager.start_job(job_id)
        with pytest.raises(ValueError, match="无法启动"):
            manager.start_job(job_id)
        await _wait_job(manager, manager.get_job(job_id))
