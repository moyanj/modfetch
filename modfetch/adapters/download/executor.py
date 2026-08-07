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
    """一次执行批次的完整报告

    聚合所有 DownloadResult 并提供统计属性，供调用方一次性
    获取批次全貌（成功/跳过/失败/总字节数），无需遍历原始列表。
    """

    results: List[DownloadResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        """总任务数"""
        return len(self.results)

    @property
    def completed(self) -> int:
        """成功且未跳过的任务数（skipped 单独统计，避免重复计数）"""
        return sum(1 for r in self.results if r.success and not r.skipped)

    @property
    def skipped(self) -> int:
        """跳过任务数（已存在且校验通过）"""
        return sum(1 for r in self.results if r.skipped)

    @property
    def failed(self) -> int:
        """失败任务数（success=False，含重试耗尽）"""
        return sum(1 for r in self.results if not r.success)

    @property
    def bytes_downloaded(self) -> int:
        """实际下载的总字节数（跳过的任务贡献 0）"""
        return sum(r.bytes_downloaded for r in self.results)

    @property
    def failures(self) -> List[DownloadResult]:
        """失败任务的完整结果列表（含错误信息，供调用方决策）"""
        return [r for r in self.results if not r.success]


class DownloadExecutor:
    """下载队列编排器

    组合 DownloaderPort（而非继承），负责并发编排而不参与下载
    细节。用固定数量 worker 的 asyncio.Queue 模型实现并发上限：
    队列本身是任务缓冲，worker 数即最大并发数。
    """

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
        #: 任务键 → DownloadResult（任务完成后留存，供 run() 汇总）
        self._results: Dict[str, DownloadResult] = {}
        #: 任务键 → 状态（pending/running/completed/skipped/failed）
        self._status: Dict[str, str] = {}
        self._workers: List[asyncio.Task] = []

    async def submit(self, task: DownloadTask) -> None:
        """提交任务（按 url+destination+filename 去重）

        去重依据：url + destination + filename 三元组。相同任务
        重复提交会直接忽略，避免同一文件被并发 worker 重复下载。
        """
        key = self._key(task)
        if key in self._status:
            logger.debug(f"[队列] '{task.filename}' 已在队列中，跳过")
            return
        self._status[key] = "pending"
        await self._queue.put(task)

    async def submit_many(self, tasks: List[DownloadTask]) -> None:
        """批量提交（逐个走 submit，天然继承去重语义）"""
        for task in tasks:
            await self.submit(task)

    def task_status(self, task: DownloadTask) -> Optional[str]:
        """查询任务状态: pending/running/completed/skipped/failed

        Returns:
            状态字符串；任务从未提交时返回 None
        """
        return self._status.get(self._key(task))

    async def run(self) -> ExecutionReport:
        """启动 worker 池并等待队列清空，返回完整报告

        并发模型：启动 max_concurrent 个 worker 协程消费队列，
        ``queue.join()`` 等待所有任务完成；最终统一取消 worker。
        失败任务不会中断整个批次——每个任务的结果独立记录在
        _results 中，由调用方通过报告决定后续处理。
        """
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
        """单个 worker：循环消费队列直到被取消

        每个任务的关键状态迁移：
        pending → running → completed/skipped/failed
        异常处理：downloader.download 只以值返回结果，理论上不抛
        异常；若意外抛出，结果不会记录——但 task_done 保证执行，
        避免队列 join 永久挂起。
        """
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
                    # 状态归一化：skipped 与 failed 都从 success 派生
                    self._status[key] = (
                        "skipped"
                        if result.skipped
                        else ("completed" if result.success else "failed")
                    )
                    if self._on_task_event is not None:
                        # 任务事件回调（如 Web 层实时推送），
                        # 由调用方注入，异常自行负责。
                        await self._on_task_event(task, result)
                finally:
                    # 无论成功失败都必须标记完成，否则 join 阻塞
                    self._queue.task_done()
            except asyncio.CancelledError:
                # 收到取消（run() 结束）即退出循环
                break

    async def _stop_workers(self) -> None:
        """取消所有 worker 并等待退出

        return_exceptions=True：worker 的 CancelledError 属于
        正常退出，不应向上传播。
        """
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

    @staticmethod
    def _key(task: DownloadTask) -> str:
        """任务去重键：url + destination + filename"""
        return f"{task.url}|{task.destination}|{task.filename}"
