"""WebSocket 事件格式契约测试

契约:
- 每个事件是 dict，必含 "event": str 与 "data": dict
- JobState._apply_event 正确折叠事件到状态快照
- 晚订阅者可回放事件历史
"""

import pytest

from modfetch.models import ModFetchConfig, ModEntry
from modfetch.plugins.base import HookContext
from modfetch.server.events import EventBridgePlugin
from modfetch.server.jobs import JobState, JobStats


@pytest.fixture
def config(make_config_dict):
    return ModFetchConfig.from_dict(make_config_dict())


class EventCollector:
    """收集广播事件的 fake broadcaster"""

    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)


class TestEventEnvelope:
    async def test_all_events_have_envelope(self, config):
        """EventBridgePlugin 产出的所有事件都有 event/data 信封"""
        collector = EventCollector()
        plugin = EventBridgePlugin(broadcaster=collector)

        ctx = HookContext(
            config=config,
            version="1.21.1",
            mod_entry=ModEntry(slug="sodium"),
            extra_data={"filename": "sodium.jar", "url": "https://x/y.jar"},
        )
        await plugin._on_config_loaded(ctx)
        await plugin._on_config_validated(ctx)
        await plugin._on_pre_resolve(ctx)
        await plugin._on_post_resolve(ctx)
        await plugin._on_pre_download(ctx)
        await plugin._on_download_progress(ctx)
        await plugin._on_post_download(ctx)
        await plugin._on_download_failed(ctx)
        await plugin._on_pre_package(ctx)
        await plugin._on_post_package(ctx)

        assert len(collector.events) > 0
        for event in collector.events:
            assert isinstance(event, dict)
            assert isinstance(event.get("event"), str), f"缺 event 字段: {event}"
            assert isinstance(event.get("data"), dict), f"缺 data 字段: {event}"

    async def test_event_names(self, config):
        """关键事件名集合契约"""
        collector = EventCollector()
        plugin = EventBridgePlugin(broadcaster=collector)
        ctx = HookContext(config=config, version="1.21.1", extra_data={})

        await plugin._on_config_loaded(ctx)
        await plugin._on_pre_download(ctx)
        await plugin._on_pre_package(ctx)

        names = [e["event"] for e in collector.events]
        assert "phase_change" in names
        assert "download_start" in names
        assert "package_start" in names


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
