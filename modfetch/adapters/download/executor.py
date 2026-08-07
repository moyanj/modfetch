"""
下载执行器（队列编排 + worker 池）

组合 DownloaderPort（而非继承），负责:
- 任务队列与并发控制
- 每个任务的明确状态（pending/running/completed/skipped/failed）
- 失败任务的完整信息（错误、重试次数、目标路径）— 由调用方决策，不静默吞没
"""

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

from loguru import logger

from modfetch.ports.downloader import (
    DownloadResult,
    DownloadTask,
    DownloaderPort,
    ProgressCallback,
)

#: 单任务完成事件回调: async (task, result)
TaskEventCallback = Callable[[DownloadTask, DownloadResult], Awaitable[None]]


@dataclass
class ExecutionReport:
    """一次执行批次的完整报告"""

    results: List[DownloadResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def completed(self) -> int:
        return sum(1 for r in self.results if r.success and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def bytes_downloaded(self) -> int:
        return sum(r.bytes_downloaded for r in self.results)

    @property
    def failures(self) -> List[DownloadResult]:
        return [r for r in self.results if not r.success]


class DownloadExecutor:
    """下载队列编排器"""

    def __init__(
        self,
        downloader: DownloaderPort,
        max_concurrent: int = 5,
        progress: Optional[ProgressCallback] = None,
        on_task_event: Optional[TaskEventCallback] = None,
    ):
        self._downloader = downloader
        self._max_concurrent = max_concurrent
        self._progress = progress
        self._on_task_event = on_task_event

        self._queue: asyncio.Queue[DownloadTask] = asyncio.Queue()
        self._results: Dict[str, DownloadResult] = {}
        self._status: Dict[str, str] = {}
        self._workers: List[asyncio.Task] = []

    async def submit(self, task: DownloadTask) -> None:
        """提交任务（按 url+destination+filename 去重）"""
        key = self._key(task)
        if key in self._status:
            logger.debug(f"[队列] '{task.filename}' 已在队列中，跳过")
            return
        self._status[key] = "pending"
        await self._queue.put(task)

    async def submit_many(self, tasks: List[DownloadTask]) -> None:
        for task in tasks:
            await self.submit(task)

    def task_status(self, task: DownloadTask) -> Optional[str]:
        """查询任务状态: pending/running/completed/skipped/failed"""
        return self._status.get(self._key(task))

    async def run(self) -> ExecutionReport:
        """启动 worker 池并等待队列清空，返回完整报告"""
        logger.info(f"[启动] 下载执行器启动，最大并发数: {self._max_concurrent}")
        self._workers = [
            asyncio.create_task(self._worker(), name=f"download-worker-{i}")
            for i in range(self._max_concurrent)
        ]
        try:
            await self._queue.join()
        finally:
            await self._stop_workers()
        return ExecutionReport(results=list(self._results.values()))

    async def _worker(self) -> None:
        while True:
            try:
                task = await self._queue.get()
                key = self._key(task)
                try:
                    self._status[key] = "running"
                    result = await self._downloader.download(
                        task, self._progress
                    )
                    self._results[key] = result
                    self._status[key] = (
                        "skipped"
                        if result.skipped
                        else ("completed" if result.success else "failed")
                    )
                    if self._on_task_event is not None:
                        await self._on_task_event(task, result)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break

    async def _stop_workers(self) -> None:
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

    @staticmethod
    def _key(task: DownloadTask) -> str:
        return f"{task.url}|{task.destination}|{task.filename}"
