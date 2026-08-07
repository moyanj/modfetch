"""JobSnapshot (JobState.to_response_dict) 字段契约测试

页面刷新后客户端通过 GET /api/jobs/{id} 恢复状态，
响应字典的字段集合与类型必须稳定。
"""

from datetime import datetime, timezone

from modfetch.server.jobs import (
    JobErrorItem,
    JobManager,
    JobResultItem,
    JobState,
    JobStats,
)


def _make_job(**overrides) -> JobState:
    job = JobState(
        id="job-1", status="pending", phase="idle",
        stats=JobStats(), config_dict={},
    )
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


class TestSnapshotShape:
    def test_top_level_fields(self):
        """顶层字段集合契约"""
        snapshot = _make_job().to_response_dict()
        assert set(snapshot.keys()) == {
            "id", "status", "phase", "stats",
            "results", "errors", "started_at", "completed_at",
        }

    def test_stats_fields(self):
        """stats 子对象字段契约"""
        snapshot = _make_job().to_response_dict()
        assert set(snapshot["stats"].keys()) == {
            "total_mods", "resolved", "downloaded", "failed", "bytes_downloaded",
        }
        assert all(isinstance(v, int) for v in snapshot["stats"].values())

    def test_empty_results_and_errors_are_none(self):
        """无结果/无错误时为 None（前端依赖此区分空与无数据）"""
        snapshot = _make_job().to_response_dict()
        assert snapshot["results"] is None
        assert snapshot["errors"] is None
        assert snapshot["started_at"] is None
        assert snapshot["completed_at"] is None

    def test_result_item_fields(self):
        job = _make_job(
            results=[
                JobResultItem(
                    filename="pack.mrpack", path="/dl/pack.mrpack", size=100,
                    format="mrpack", mc_version="1.21.1", loader="fabric",
                )
            ]
        )
        item = job.to_response_dict()["results"][0]
        assert set(item.keys()) == {
            "filename", "path", "size", "format", "mc_version", "loader",
        }

    def test_error_item_fields(self):
        job = _make_job(
            errors=[JobErrorItem(code="E300", message="boom", context=None)]
        )
        item = job.to_response_dict()["errors"][0]
        assert set(item.keys()) == {"code", "message", "context"}

    def test_timestamps_iso_format(self):
        now = datetime.now(timezone.utc)
        job = _make_job(started_at=now, completed_at=now)
        snapshot = job.to_response_dict()
        # ISO 格式可被 datetime.fromisoformat 解析
        datetime.fromisoformat(snapshot["started_at"])
        datetime.fromisoformat(snapshot["completed_at"])


class TestJobManager:
    def test_create_and_get(self):
        manager = JobManager()
        job_id = manager.create_job({"minecraft": {"version": ["1.21.1"]}})
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.phase == "idle"

    def test_get_unknown_returns_none(self):
        assert JobManager().get_job("nonexistent") is None

    def test_extract_config_summary(self):
        """配置摘要提取契约"""
        summary = JobManager()._extract_config_summary(
            {
                "minecraft": {
                    "version": ["1.21.1", "1.20.4"],
                    "mod_loader": ["fabric", "forge"],
                    "mods": ["a", "b", "c"],
                }
            }
        )
        assert summary == {
            "versions": ["1.21.1", "1.20.4"],
            "loaders": ["fabric", "forge"],
            "mod_count": 3,
        }

    def test_extract_config_summary_scalar_normalization(self):
        """标量值归一化为列表"""
        summary = JobManager()._extract_config_summary(
            {"minecraft": {"version": "1.21.1", "mod_loader": "fabric", "mods": []}}
        )
        assert summary["versions"] == ["1.21.1"]
        assert summary["loaders"] == ["fabric"]

    def test_extract_config_summary_no_minecraft(self):
        assert JobManager()._extract_config_summary({}) == {}


class TestLateSubscriberReplay:
    async def test_finished_job_replays_history(self):
        """已完成任务的晚订阅者立即收到历史回放后结束"""
        manager = JobManager()
        job_id = manager.create_job({})
        job = manager.get_job(job_id)
        await job.broadcast({"event": "job_started", "data": {"job_id": job_id}})
        await job.broadcast(
            {"event": "job_complete", "data": {"results": [], "duration_ms": 1}}
        )

        events = [e async for e in manager.subscribe(job_id)]
        assert [e["event"] for e in events] == ["job_started", "job_complete"]

    async def test_unknown_job_yields_nothing(self):
        events = [e async for e in JobManager().subscribe("nonexistent")]
        assert events == []
