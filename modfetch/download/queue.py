"""
下载任务队列

实现优先级队列、任务去重、队列状态监控。
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Priority(Enum):
    """下载优先级"""

    HIGH = 0
    NORMAL = 1
    LOW = 2


@dataclass(order=True)
class DownloadTask:
    """下载任务"""

    priority: int = field(compare=True)
    url: str = field(compare=False)
    filename: str = field(compare=False)
    download_dir: str = field(compare=False)
    sha1: Optional[str] = field(default=None, compare=False)
    category: str = field(default="files", compare=False)

    def __init__(
        self,
        url: str,
        filename: str,
        download_dir: str,
        sha1: Optional[str] = None,
        category: str = "files",
        priority: Priority = Priority.NORMAL,
    ):
        self.priority = priority.value
        self.url = url
        self.filename = filename
        self.download_dir = download_dir
        self.sha1 = sha1
        self.category = category


class DownloadQueue:
    """下载队列"""

    def __init__(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._tasks: set[str] = set()  # 用于去重
        self._total_queued = 0

    async def put(
        self,
        url: str,
        filename: str,
        download_dir: str,
        sha1: Optional[str] = None,
        category: str = "files",
        priority: Priority = Priority.NORMAL,
    ) -> bool:
        """
        添加任务到队列

        Returns:
            True 如果任务是新添加的，False 如果是重复任务
        """
        task_key = f"{url}:{filename}"

        if task_key in self._tasks:
            return False

        self._tasks.add(task_key)
        task = DownloadTask(
            url=url,
            filename=filename,
            download_dir=download_dir,
            sha1=sha1,
            category=category,
            priority=priority,
        )
        await self._queue.put(task)
        self._total_queued += 1
        return True

    async def get(self) -> DownloadTask:
        """获取下一个任务"""
        return await self._queue.get()

    def task_done(self):
        """标记任务完成"""
        self._queue.task_done()

    def qsize(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()

    async def join(self):
        """等待所有任务完成"""
        await self._queue.join()

    def is_duplicate(self, url: str, filename: str) -> bool:
        """检查是否是重复任务"""
        task_key = f"{url}:{filename}"
        return task_key in self._tasks

    def get_stats(self) -> dict:
        """获取队列统计"""
        return {
            "pending": self.qsize(),
            "total_queued": self._total_queued,
        }

    def clear(self):
        """清空队列"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._tasks.clear()
