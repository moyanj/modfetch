"""WebSocket 事件格式契约测试

事件信封（event/data）与 JobState 折叠契约。
统一事件的信封与字段契约见 test_job_event_sink.py。
"""

import pytest

from modfetch.server.jobs import JobState, JobStats


def _make_job() -> JobState:
    return JobState(
        id="job-1", status="pending", phase="idle",
        stats=JobStats(), config_dict={},
    )


class TestJobStateFolding:
    async def test_job_started_sets_running(self):
        job = _make_job()
        await job.broadcast({"event": "job_started", "data": {"job_id": "job-1"}})
        assert job.status == "running"

    async def test_phase_change(self):
        job = _make_job()
        await job.broadcast({"event": "phase_change", "data": {"phase": "download"}})
        assert job.phase == "download"

    async def test_stats_update(self):
        job = _make_job()
        await job.broadcast(
            {
                "event": "stats_update",
                "data": {
                    "total": 10, "completed": 3, "failed": 1,
                    "bytes_downloaded": 1024,
                },
            }
        )
        assert job.stats.total_mods == 10
        assert job.stats.downloaded == 3
        assert job.stats.failed == 1
        assert job.stats.bytes_downloaded == 1024

    async def test_resolve_complete_increments(self):
        job = _make_job()
        await job.broadcast({"event": "resolve_complete", "data": {}})
        await job.broadcast({"event": "resolve_complete", "data": {}})
        assert job.stats.resolved == 2

    async def test_job_complete_sets_results(self):
        job = _make_job()
        await job.broadcast(
            {
                "event": "job_complete",
                "data": {
                    "results": [
                        {
                            "filename": "pack.mrpack",
                            "path": "/dl/pack.mrpack",
                            "size": 100,
                            "format": "mrpack",
                            "mc_version": "1.21.1",
                            "loader": "fabric",
                        }
                    ]
                },
            }
        )
        assert job.status == "completed"
        assert job.phase == "idle"
        assert len(job.results) == 1
        assert job.results[0].filename == "pack.mrpack"

    async def test_job_failed_dedup_error(self):
        """相同错误不重复写入 errors"""
        job = _make_job()
        error_event = {
            "event": "job_failed",
            "data": {"error": {"code": "E300", "message": "boom"}},
        }
        await job.broadcast(error_event)
        await job.broadcast(error_event)
        assert job.status == "failed"
        assert len(job.errors) == 1

    async def test_event_history_capped(self):
        """事件历史上限 512 条"""
        job = _make_job()
        for _ in range(600):
            await job.broadcast({"event": "phase_change", "data": {"phase": "x"}})
        assert len(job.event_history) == 512
