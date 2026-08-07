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
    """作业应用服务（内存实现）

    负责 Web 作业的创建/启动/查询/订阅：
    - 作业以 JobState 存于内存 dict，随进程生命周期
    - 构建执行委托 BuildApplicationService，事件经 JobEventSink
      折叠入 JobState（广播 + 历史回放）
    """

    def __init__(self, service_factory: ServiceFactory = create_build_service):
        self._jobs: dict[str, JobState] = {}
        self._service_factory = service_factory
        self._config_service = ConfigService()

    # -- 生命周期 -----------------------------------------------------------

    def create_job(self, config_dict: dict[str, object]) -> str:
        """创建新任务，返回 job_id

        仅登记 pending 状态，不启动执行；启动由 start_job 触发。
        """
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
        """获取任务状态（不存在返回 None）"""
        return self._jobs.get(job_id)

    def start_job(self, job_id: str) -> None:
        """启动任务 — 在后台 asyncio.Task 中运行

        前置条件：任务必须存在且处于 pending（重复启动抛 ValueError）。

        Raises:
            ValueError: 任务不存在，或状态非 pending
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"任务 {job_id} 不存在")

        if job.status != "pending":
            raise ValueError(f"任务 {job_id} 状态为 {job.status}，无法启动")

        # 状态转移: pending → running，并记录开始时间
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        # 后台任务引用存于 JobState，供生命周期管理
        job._task = asyncio.create_task(self._run_job(job))
        logger.info(f"启动任务 {job_id}")

    async def _run_job(self, job: JobState) -> None:
        """运行任务 — 解析配置、组装服务、执行构建

        核心流程：
        1. 提取配置摘要并构建 JobEventSink（事件广播回 JobState）
        2. 解析配置为 ModFetchConfig
        3. 按配置并发参数组装 BuildApplicationService
        4. 执行构建（跳过远程校验，已在创建时校验）
        5. 依据结果折叠错误 / 标记完成

        异常处理：
        - ModFetchError: 按错误码折叠为 JobErrorItem 并广播 job_failed
        - 其他异常: 统一为 E500 折叠并广播
        """
        config_summary = self._extract_config_summary(job.config_dict)
        # 事件经 sink → job.broadcast，同时推给订阅者并折叠到状态
        sink = JobEventSink(
            job.broadcast, job.id, config_summary=config_summary
        )

        try:
            # 解析配置
            config = self._config_service.parse(job.config_dict)

            # 组装构建服务（远程校验已在创建任务时完成）
            # max_concurrent 控制下载并发度，由 BuildApplicationService 内部执行
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
                # 汇总结构化错误（job_failed 事件已由 sink 广播，此处补全 detail）
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
            # 领域错误: 折叠为对应错误码并广播 job_failed
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
            # 未知异常: 统一降级为 E500
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

        行为：
        - 先回放 event_history（覆盖晚订阅者，含已终态任务）
        - 任务已终态则不再新建队列
        - 否则注册 asyncio.Queue 并持续消费，终态事件后退出并注销队列
        """
        job = self._jobs.get(job_id)
        if job is None:
            return

        # 回放历史事件，晚订阅的客户端也能拿到完整进度
        for event in job.event_history:
            yield event

        if job.status in ("completed", "failed"):
            # 任务已终结: 历史即全部，无需实时订阅
            return

        # 创建订阅者队列（事件经 broadcast() 投递到所有活跃队列）
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        job._subscribers.append(queue)

        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("event") in ("job_complete", "job_failed"):
                    # 终态事件后退出，避免挂起
                    break
        finally:
            # 确保异常/退出时移除队列，防止泄漏
            if queue in job._subscribers:
                job._subscribers.remove(queue)

    # -- 辅助 -----------------------------------------------------------------

    def _extract_config_summary(
        self, config_dict: dict[str, object]
    ) -> dict[str, object]:
        """从配置字典中提取摘要信息

        产出 job_started 事件附带的 config_summary（版本/加载器/模组数），
        供前端在作业开始时展示；版本与加载器缺省为 fabric/空。
        """
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
