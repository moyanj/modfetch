"""
作业应用服务

Web 作业管理 — 只做: 创建/启动/查询/订阅。
构建执行统一委托 BuildApplicationService:
- 事件经 JobEventSink 流入 JobState（折叠 + 回放）
- 结果来自 BuildResult.outputs（不再做文件系统扫描）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable, Optional

from loguru import logger

from modfetch.adapters.events.job_sink import JobEventSink
from modfetch.adapters.jobs.state import (
    JobErrorItem,
    JobState,
    JobStats,
)
from modfetch.application.build_service import BuildApplicationService
from modfetch.application.config_service import ConfigService
from modfetch.composition import create_build_service
from modfetch.domain.errors import ModFetchError

#: BuildApplicationService 工厂（测试注入用）
ServiceFactory = Callable[..., BuildApplicationService]


class JobApplicationService:
    """作业应用服务（内存实现）"""

    def __init__(self, service_factory: ServiceFactory = create_build_service):
        self._jobs: dict[str, JobState] = {}
        self._service_factory = service_factory
        self._config_service = ConfigService()

    # -- 生命周期 -----------------------------------------------------------

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
        """运行任务 — 解析配置、组装服务、执行构建"""
        config_summary = self._extract_config_summary(job.config_dict)
        sink = JobEventSink(
            job.broadcast, job.id, config_summary=config_summary
        )

        try:
            # 解析配置
            config = self._config_service.parse(job.config_dict)

            # 组装构建服务（远程校验已在创建任务时完成）
            service = self._service_factory(
                event_sink=sink,
                max_concurrent=config.max_concurrent,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
            )

            result = await service.execute(
                config, job_id=job.id, skip_remote_validation=True
            )

            job.completed_at = datetime.now(timezone.utc)

            if not result.success:
                # 汇总结构化错误（job_failed 事件已由 sink 广播）
                for error in result.errors:
                    item = JobErrorItem(
                        code=error.code,
                        message=error.message,
                        context=dict(error.context),
                    )
                    if not any(
                        e.code == item.code and e.message == item.message
                        for e in job.errors
                    ):
                        job.errors.append(item)
                logger.error(f"任务 {job.id} 失败: {len(result.errors)} 个错误")
            else:
                logger.success(f"任务 {job.id} 完成")

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

    # -- 事件订阅 -------------------------------------------------------------

    async def subscribe(
        self, job_id: str
    ) -> AsyncGenerator[dict[str, object], None]:
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

    # -- 辅助 -----------------------------------------------------------------

    def _extract_config_summary(
        self, config_dict: dict[str, object]
    ) -> dict[str, object]:
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


#: 向后兼容别名
JobManager = JobApplicationService
