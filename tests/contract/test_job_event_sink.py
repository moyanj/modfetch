"""JobEventSink 契约测试: 统一 BuildEvent → WS 事件流翻译"""

import pytest

from modfetch.adapters.events import JobEventSink
from modfetch.domain.events import BuildEvent, EventType
from modfetch.adapters.jobs import JobState, JobStats


class Collector:
    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        return [e["event"] for e in self.events]


async def _pub(sink, et, payload=None):
    await sink.publish(
        BuildEvent(job_id="job-1", event_type=et, payload=payload or {})
    )


class TestTranslation:
    async def test_lifecycle_event_names(self):
        """统一事件翻译为前端契约事件名"""
        collector = Collector()
        sink = JobEventSink(collector, "job-1")

        await _pub(sink, EventType.BUILD_STARTED)
        await _pub(sink, EventType.CONFIG_VALIDATED)
        await _pub(sink, EventType.PLAN_CREATED, {"artifacts": 5})
        await _pub(sink, EventType.RESOLVE_STARTED, {"mod_slug": "sodium"})
        await _pub(sink, EventType.RESOLVE_COMPLETED, {"mod_slug": "sodium"})
        await _pub(sink, EventType.DOWNLOAD_COMPLETED,
                   {"filename": "a.jar", "size": 100})
        await _pub(sink, EventType.PACKAGE_STARTED, {"format": "mrpack"})
        await _pub(sink, EventType.PACKAGE_COMPLETED,
                   {"path": "/dl/p.mrpack", "size": 200, "format": "mrpack"})
        await _pub(sink, EventType.BUILD_COMPLETED, {"outputs": []})

        names = collector.names
        assert names[0] == "job_started"
        assert "phase_change" in names
        assert "stats_update" in names
        assert "resolve_start" in names
        assert "resolve_complete" in names
        assert "download_complete" in names
        assert "package_start" in names
        assert "package_complete" in names
        assert names[-1] == "job_complete"

    async def test_unified_fields(self):
        """字段统一: total/completed/bytes_downloaded 来自真实数据"""
        collector = Collector()
        sink = JobEventSink(collector, "job-1")

        await _pub(sink, EventType.PLAN_CREATED, {"artifacts": 3})
        await _pub(sink, EventType.DOWNLOAD_COMPLETED,
                   {"filename": "a.jar", "size": 512})
        await _pub(sink, EventType.DOWNLOAD_FAILED, {"filename": "b.jar",
                                                      "error": "boom"})

        stats_events = [
            e["data"] for e in collector.events if e["event"] == "stats_update"
        ]
        final = stats_events[-1]
        assert final["total"] == 3
        assert final["completed"] == 1
        assert final["failed"] == 1
        assert final["bytes_downloaded"] == 512

        # download_failed 的错误字段来自真实数据而非硬编码
        failed = next(
            e for e in collector.events if e["event"] == "download_failed"
        )
        assert failed["data"]["error"]["message"] == "boom"

    async def test_progress_percent_and_bytes(self):
        """download_progress 携带真实字节数与百分比"""
        collector = Collector()
        sink = JobEventSink(collector, "job-1")
        await _pub(
            sink, EventType.DOWNLOAD_PROGRESS,
            {"filename": "a.jar", "bytes_downloaded": 50, "bytes_total": 200},
        )
        data = collector.events[0]["data"]
        assert data["bytes_downloaded"] == 50
        assert data["bytes_total"] == 200
        assert data["percent"] == 25.0

    async def test_output_result_mapping(self):
        """BUILD_COMPLETED 的 outputs 映射为 JobResultItem 兼容格式"""
        collector = Collector()
        sink = JobEventSink(collector, "job-1")
        await _pub(
            sink, EventType.BUILD_COMPLETED,
            {
                "outputs": [
                    {
                        "path": "/dl/Pack_1.0.0_MC1.21.1-fabric.mrpack",
                        "format": "mrpack",
                        "size": 100,
                        "target": "1.21.1-fabric",
                    }
                ]
            },
        )
        result = collector.events[0]["data"]["results"][0]
        assert result == {
            "filename": "Pack_1.0.0_MC1.21.1-fabric.mrpack",
            "path": "/dl/Pack_1.0.0_MC1.21.1-fabric.mrpack",
            "size": 100,
            "format": "mrpack",
            "mc_version": "1.21.1",
            "loader": "fabric",
        }

    async def test_envelope_and_sequence(self):
        """信封契约: event/data + 单调递增 sequence"""
        collector = Collector()
        sink = JobEventSink(collector, "job-1")
        for _ in range(3):
            await _pub(sink, EventType.RESOLVE_STARTED, {})

        seqs = [e["data"]["sequence"] for e in collector.events]
        assert seqs == [1, 2, 3]
        for event in collector.events:
            assert isinstance(event["event"], str)
            assert isinstance(event["data"], dict)
            assert event["data"]["job_id"] == "job-1"


class TestJobStateIntegration:
    async def test_folding_with_job_state(self):
        """翻译后的事件可被 JobState 正确折叠"""
        job = JobState(
            id="job-1", status="pending", phase="idle",
            stats=JobStats(), config_dict={},
        )
        sink = JobEventSink(job.broadcast, "job-1")

        await _pub(sink, EventType.BUILD_STARTED)
        assert job.status == "running"

        await _pub(sink, EventType.PLAN_CREATED, {"artifacts": 2})
        assert job.stats.total_mods == 2

        await _pub(sink, EventType.DOWNLOAD_COMPLETED,
                   {"filename": "a.jar", "size": 100})
        assert job.stats.downloaded == 1
        assert job.stats.bytes_downloaded == 100

        await _pub(
            sink, EventType.BUILD_COMPLETED,
            {
                "outputs": [
                    {
                        "path": "/dl/p.mrpack", "format": "mrpack",
                        "size": 1, "target": "1.21.1-fabric",
                    }
                ]
            },
        )
        assert job.status == "completed"
        assert len(job.results) == 1
        assert job.results[0].loader == "fabric"


class TestJobStateFolding:
    """JobState 对翻译后事件的直接折叠契约"""

    def _make_job(self) -> JobState:
        return JobState(
            id="job-1", status="pending", phase="idle",
            stats=JobStats(), config_dict={},
        )

    async def test_phase_change(self):
        job = self._make_job()
        await job.broadcast({"event": "phase_change", "data": {"phase": "download"}})
        assert job.phase == "download"

    async def test_stats_update(self):
        job = self._make_job()
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
        job = self._make_job()
        await job.broadcast({"event": "resolve_complete", "data": {}})
        await job.broadcast({"event": "resolve_complete", "data": {}})
        assert job.stats.resolved == 2

    async def test_job_failed_dedup_error(self):
        """相同错误不重复写入 errors"""
        job = self._make_job()
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
        job = self._make_job()
        for _ in range(600):
            await job.broadcast({"event": "phase_change", "data": {"phase": "x"}})
        assert len(job.event_history) == 512
