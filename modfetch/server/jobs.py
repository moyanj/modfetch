"""
异步任务管理器

在内存中管理构建任务的生命周期，包括:
- 创建任务 (create_job)
- 启动任务 (start_job) — 后台 asyncio.Task 运行 ServerOrchestrator
- 查询状态 (get_job)
- 订阅事件流 (subscribe) — AsyncGenerator 供 WebSocket 消费
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from loguru import logger

from modfetch.exceptions import ModFetchError
from modfetch.models import ModFetchConfig
from modfetch.plugins import PluginManager
from modfetch.server.events import EventBridgePlugin, ServerOrchestrator

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class JobStats:
    """任务统计"""

    total_mods: int = 0
    resolved: int = 0
    downloaded: int = 0
    failed: int = 0
    bytes_downloaded: int = 0


@dataclass
class JobResultItem:
    """任务结果项"""

    filename: str
    path: str
    size: int
    format: str
    mc_version: str
    loader: str


@dataclass
class JobErrorItem:
    """任务错误项"""

    code: str
    message: str
    context: Optional[dict[str, object]] = None


@dataclass
class JobState:
    """
    任务状态

    每个任务维护一组订阅者队列 (asyncio.Queue)，事件通过 broadcast()
    推送到所有订阅者。WebSocket 端点通过 subscribe() 创建新队列并消费事件。
    """

    id: str
    status: str  # pending | running | completed | failed
    phase: str  # idle | resolve | download | package
    stats: JobStats
    config_dict: dict[str, object]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: list[JobResultItem] = field(default_factory=list)
    errors: list[JobErrorItem] = field(default_factory=list)
    event_history: list[dict[str, object]] = field(default_factory=list)

    # 事件订阅
    _subscribers: list[asyncio.Queue[dict[str, object]]] = field(
        default_factory=list
    )
    # 后台任务
    _task: Optional[asyncio.Task[None]] = None
    # 当前版本/加载器 (由 ServerOrchestrator 更新)
    current_version: str = ""
    current_loader: str = ""

    @property
    def duration_ms(self) -> int:
        """任务持续时间 (毫秒)"""
        if self.started_at is None:
            return 0
        end = self.completed_at or datetime.now(timezone.utc)
        return int((end - self.started_at).total_seconds() * 1000)

    async def broadcast(self, event: dict[str, object]) -> None:
        """将事件推送到所有订阅者队列"""
        self._record_event(event)
        self._apply_event(event)
        for queue in self._subscribers:
            await queue.put(event)

    def _record_event(self, event: dict[str, object]) -> None:
        """记录任务事件历史，供晚订阅的客户端回放。"""
        self.event_history.append(event)
        if len(self.event_history) > 512:
            self.event_history.pop(0)

    def _apply_event(self, event: dict[str, object]) -> None:
        """将事件折叠到当前任务状态快照。"""
        event_type = event.get("event")
        data = event.get("data")
        if not isinstance(data, dict):
            return

        if event_type == "job_started":
            self.status = "running"
            return

        if event_type == "phase_change":
            phase = data.get("phase")
            if isinstance(phase, str):
                self.phase = phase
            return

        if event_type == "stats_update":
            total = _safe_int(data.get("total"), self.stats.total_mods)
            completed = _safe_int(data.get("completed"), self.stats.downloaded)
            failed = _safe_int(data.get("failed"), self.stats.failed)
            bytes_downloaded = _safe_int(
                data.get("bytes_downloaded"), self.stats.bytes_downloaded
            )
            self.stats.total_mods = total
            self.stats.downloaded = completed
            self.stats.failed = failed
            self.stats.bytes_downloaded = bytes_downloaded
            return

        if event_type == "resolve_complete":
            self.stats.resolved += 1
            return

        if event_type == "job_complete":
            self.status = "completed"
            self.phase = "idle"
            self.results = _parse_results(data.get("results"))
            return

        if event_type == "job_failed":
            self.status = "failed"
            self.phase = "idle"
            error = _parse_error(data.get("error"))
            if error is not None and not _has_error(self.errors, error):
                self.errors.append(error)

    def to_response_dict(self) -> dict[str, object]:
        """转换为 API 响应字典"""
        def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
            if dt is None:
                return None
            return dt.isoformat()

        return {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "stats": {
                "total_mods": self.stats.total_mods,
                "resolved": self.stats.resolved,
                "downloaded": self.stats.downloaded,
                "failed": self.stats.failed,
                "bytes_downloaded": self.stats.bytes_downloaded,
            },
            "results": (
                [
                    {
                        "filename": r.filename,
                        "path": r.path,
                        "size": r.size,
                        "format": r.format,
                        "mc_version": r.mc_version,
                        "loader": r.loader,
                    }
                    for r in self.results
                ]
                if self.results
                else None
            ),
            "errors": (
                [
                    {
                        "code": e.code,
                        "message": e.message,
                        "context": e.context,
                    }
                    for e in self.errors
                ]
                if self.errors
                else None
            ),
            "started_at": fmt_dt(self.started_at),
            "completed_at": fmt_dt(self.completed_at),
        }


# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------


class JobManager:
    """
    任务管理器

    在内存中管理所有任务。单例模式 — 由 FastAPI app 持有。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def create_job(self, config_dict: dict[str, object]) -> str:
        """创建新任务，返回 job_id"""
        job_id = str(uuid.uuid4())
        job = JobState(
            id=job_id,
            status="pending",
            phase="idle",
            stats=JobStats(),
            config_dict=config_dict,
        )
        self._jobs[job_id] = job
        logger.info(f"创建任务 {job_id}")
        return job_id

    def get_job(self, job_id: str) -> Optional[JobState]:
        """获取任务状态"""
        return self._jobs.get(job_id)

    def start_job(self, job_id: str) -> None:
        """启动任务 — 在后台 asyncio.Task 中运行"""
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"任务 {job_id} 不存在")

        if job.status != "pending":
            raise ValueError(f"任务 {job_id} 状态为 {job.status}，无法启动")

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job._task = asyncio.create_task(self._run_job(job))
        logger.info(f"启动任务 {job_id}")

    async def _run_job(self, job: JobState) -> None:
        """运行任务 — 解析配置、创建编排器、执行"""
        start_time = time.monotonic()

        # 广播 job_started
        config_summary = self._extract_config_summary(job.config_dict)
        await job.broadcast(
            {
                "event": "job_started",
                "data": {"job_id": job.id, "config_summary": config_summary},
            }
        )

        try:
            # 解析配置
            config = ModFetchConfig.from_dict(job.config_dict)
            job.stats.total_mods = len(config.minecraft.mods)

            # 创建插件管理器并注册事件桥接插件
            plugin_manager = PluginManager()
            event_bridge = EventBridgePlugin(broadcaster=job.broadcast)
            plugin_manager.register_plugin(event_bridge)

            # 创建并运行 ServerOrchestrator
            orchestrator = ServerOrchestrator(
                config=config,
                plugin_manager=plugin_manager,
                broadcaster=job.broadcast,
                on_version_loader=lambda v, l: self._update_version_loader(
                    job, v, l
                ),
            )
            await orchestrator.run()

            # 收集结果
            job.results = self._collect_results(orchestrator)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.phase = "idle"

            duration_ms = int((time.monotonic() - start_time) * 1000)
            await job.broadcast(
                {
                    "event": "job_complete",
                    "data": {
                        "results": [
                            {
                                "filename": r.filename,
                                "path": r.path,
                                "size": r.size,
                                "format": r.format,
                                "mc_version": r.mc_version,
                                "loader": r.loader,
                            }
                            for r in job.results
                        ],
                        "duration_ms": duration_ms,
                    },
                }
            )
            logger.success(f"任务 {job.id} 完成 ({duration_ms}ms)")

        except ModFetchError as e:
            job.errors.append(
                JobErrorItem(code=e.code, message=e.message, context=e.context)
            )
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            await job.broadcast(
                {
                    "event": "job_failed",
                    "data": {"error": {"code": e.code, "message": e.message}},
                }
            )
            logger.error(f"任务 {job.id} 失败: {e}")

        except Exception as e:
            job.errors.append(
                JobErrorItem(code="E500", message=str(e), context=None)
            )
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            await job.broadcast(
                {
                    "event": "job_failed",
                    "data": {"error": {"code": "E500", "message": str(e)}},
                }
            )
            logger.error(f"任务 {job.id} 异常: {e}")

    async def subscribe(self, job_id: str) -> AsyncGenerator[dict[str, object], None]:
        """
        订阅任务事件流

        返回 AsyncGenerator，yield 事件字典。
        当收到 job_complete 或 job_failed 事件时停止。
        如果任务已完成/失败，立即 yield 最终状态。
        """
        job = self._jobs.get(job_id)
        if job is None:
            return

        for event in job.event_history:
            yield event

        if job.status in ("completed", "failed"):
            return

        # 创建订阅者队列
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        job._subscribers.append(queue)

        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("event") in ("job_complete", "job_failed"):
                    break
        finally:
            if queue in job._subscribers:
                job._subscribers.remove(queue)

    # -- 辅助方法 --------------------------------------------------------

    def _update_version_loader(self, job: JobState, version: str, loader: str) -> None:
        """更新任务的当前版本/加载器"""
        job.current_version = version
        job.current_loader = loader

    def _extract_config_summary(self, config_dict: dict[str, object]) -> dict[str, object]:
        """从配置字典中提取摘要信息"""
        minecraft = config_dict.get("minecraft")
        if not isinstance(minecraft, dict):
            return {}

        versions = minecraft.get("version", [])
        loaders = minecraft.get("mod_loader", "fabric")
        mods = minecraft.get("mods", [])

        return {
            "versions": versions if isinstance(versions, list) else [versions],
            "loaders": loaders if isinstance(loaders, list) else [loaders],
            "mod_count": len(mods) if isinstance(mods, list) else 0,
        }

    def _collect_results(self, orchestrator: ServerOrchestrator) -> list[JobResultItem]:
        """从编排器收集输出结果"""
        results: list[JobResultItem] = []
        download_dir = orchestrator.config.output.download_dir

        # 遍历输出目录查找生成的文件
        if not os.path.exists(download_dir):
            return results

        for version in orchestrator.config.minecraft.version:
            loaders = orchestrator.config.minecraft.mod_loader
            if not isinstance(loaders, list):
                loaders = [loaders]

            for loader in loaders:
                for fmt in orchestrator.config.output.format:
                    # 查找 mrpack / zip 文件
                    if fmt.value == "mrpack":
                        pattern = f"MC{version}-{loader.value}"
                    else:
                        pattern = f"archive-{version}-{loader.value}"

                    for filename in os.listdir(download_dir):
                        filepath = os.path.join(download_dir, filename)
                        if not os.path.isfile(filepath):
                            continue
                        if pattern in filename and (
                            filename.endswith(".mrpack")
                            or filename.endswith(".zip")
                        ):
                            try:
                                size = os.path.getsize(filepath)
                            except OSError:
                                size = 0
                            results.append(
                                JobResultItem(
                                    filename=filename,
                                    path=filepath,
                                    size=size,
                                    format=fmt.value,
                                    mc_version=version,
                                    loader=loader.value,
                                )
                            )

        return results


def _safe_int(value: object, default: int = 0) -> int:
    """安全转换整数。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_results(value: object) -> list[JobResultItem]:
    """从事件数据解析结果列表。"""
    if not isinstance(value, list):
        return []

    results: list[JobResultItem] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        path = item.get("path")
        fmt = item.get("format")
        mc_version = item.get("mc_version")
        loader = item.get("loader")
        if not all(
            isinstance(field, str)
            for field in (filename, path, fmt, mc_version, loader)
        ):
            continue
        results.append(
            JobResultItem(
                filename=filename,
                path=path,
                size=_safe_int(item.get("size")),
                format=fmt,
                mc_version=mc_version,
                loader=loader,
            )
        )
    return results


def _parse_error(value: object) -> Optional[JobErrorItem]:
    """从事件数据解析错误对象。"""
    if not isinstance(value, dict):
        return None

    code = value.get("code")
    message = value.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        return None

    context = value.get("context")
    if context is not None and not isinstance(context, dict):
        context = None
    return JobErrorItem(code=code, message=message, context=context)


def _has_error(errors: list[JobErrorItem], target: JobErrorItem) -> bool:
    """判断错误是否已存在，避免事件折叠重复写入。"""
    return any(
        error.code == target.code and error.message == target.message
        for error in errors
    )
