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
        for queue in self._subscribers:
            await queue.put(event)

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

        # 如果任务已结束，直接返回最终状态
        if job.status in ("completed", "failed"):
            if job.status == "completed":
                yield {
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
                        "duration_ms": job.duration_ms,
                    },
                }
            else:
                error = job.errors[-1] if job.errors else None
                yield {
                    "event": "job_failed",
                    "data": {
                        "error": {
                            "code": error.code if error else "E500",
                            "message": error.message if error else "Unknown error",
                        }
                    },
                }
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
