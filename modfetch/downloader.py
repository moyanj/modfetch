import asyncio
import os
from typing import Optional, Tuple, List
from dataclasses import dataclass
import aiohttp
import aiofiles


@dataclass
class DownloadTask:
    """下载任务数据类"""

    url: str
    filename: str
    download_dir: str
    category: str


class AsyncDownloader:
    """
    异步并行下载器类
    负责管理下载队列、并发控制和文件写入
    """

    def __init__(
        self, max_concurrent: int = 5, print_lock: Optional[asyncio.Lock] = None
    ):
        """
        初始化下载器

        Args:
            max_concurrent: 最大并发下载数
            print_lock: 可选的打印锁，用于线程安全输出
        """
        self.max_concurrent = max_concurrent
        self.download_queue = asyncio.Queue()
        self.active_downloads = 0
        self.completed_downloads = 0
        self.failed_downloads: List[Tuple[str, Exception]] = []
        self.print_lock = print_lock or asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self._workers: List[asyncio.Task] = []
        self._is_running = False

    @property
    def session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def enqueue_download(
        self, url: str, filename: str, download_dir: str, category: str = "files"
    ) -> None:
        """
        将下载任务加入队列

        Args:
            url: 下载URL
            filename: 文件名
            download_dir: 下载目录
            category: 文件类别（用于日志）
        """
        task = DownloadTask(url, filename, download_dir, category)
        await self.download_queue.put(task)
        await self._safe_print(f"[队列] {category} '{filename}' 已加入下载队列")

    async def download_file(self, task: DownloadTask) -> None:
        """
        下载单个文件

        Args:
            task: 下载任务
        """
        file_path = os.path.join(task.download_dir, task.filename)

        # 确保目录存在
        os.makedirs(task.download_dir, exist_ok=True)

        await self._safe_print(f"[开始] 下载 {task.category}: {task.filename}")

        # 处理本地文件
        if task.url.startswith("file://"):
            await self._handle_local_file(task, file_path)
            return

        # 检查文件是否已存在（简单存在性检查，不进行校验）
        if os.path.exists(file_path):
            await self._safe_print(f"[跳过] {task.filename} 已存在")
            self.completed_downloads += 1
            return

        try:
            await self._download_remote_file(task, file_path)
        except Exception as e:
            await self._handle_download_error(task, e, file_path)

    async def _handle_local_file(self, task: DownloadTask, file_path: str) -> None:
        """处理本地文件复制"""
        try:
            import shutil

            src_path = task.url[7:]  # 移除 "file://" 前缀

            if os.path.isdir(src_path):
                if os.path.exists(file_path):
                    shutil.rmtree(file_path)
                shutil.copytree(src_path, file_path)
            else:
                shutil.copy2(src_path, file_path)

            await self._safe_print(f"[完成] 本地文件 {task.filename} 复制完成")
            self.completed_downloads += 1

        except Exception as e:
            await self._safe_print(f"[错误] 复制本地文件失败 {task.filename}: {e}")
            self.failed_downloads.append((task.filename, e))

    async def _download_remote_file(self, task: DownloadTask, file_path: str) -> None:
        """下载远程文件"""
        async with self.session.get(task.url, ssl=False) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {task.url}")

            total_size = int(response.headers.get("Content-Length", 0))
            await self._safe_print(
                f"[信息] 文件大小: {total_size / (1024 * 1024):.2f} MB"
            )

            async with aiofiles.open(file_path, "wb") as file:
                downloaded = 0
                last_percent = 0

                async for chunk in response.content.iter_chunked(8192):
                    await file.write(chunk)
                    downloaded += len(chunk)

                    # 显示下载进度（每5%更新一次）
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        if percent - last_percent >= 5:
                            await self._safe_print(
                                f"[进度] {task.filename}: {percent:.1f}%"
                            )
                            last_percent = percent

                # 确保显示100%
                if total_size > 0:
                    await self._safe_print(f"[进度] {task.filename}: 100.0%")

            await self._safe_print(f"[完成] {task.filename} 下载完成")
            self.completed_downloads += 1

    async def _handle_download_error(
        self, task: DownloadTask, error: Exception, file_path: str
    ) -> None:
        """处理下载错误"""
        await self._safe_print(f"[错误] 下载 {task.filename} 失败: {error}")
        self.failed_downloads.append((task.filename, error))

        # 清理不完整的文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

    async def _download_worker(self) -> None:
        """下载工作线程"""
        while True:
            try:
                task = await self.download_queue.get()
                self.active_downloads += 1

                try:
                    await self.download_file(task)
                finally:
                    self.active_downloads -= 1
                    self.download_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._safe_print(f"[错误] 工作线程异常: {e}")
                self.active_downloads -= 1
                self.download_queue.task_done()

    async def start(self) -> None:
        """启动下载器"""
        if self._is_running:
            return

        self._is_running = True
        await self._safe_print(f"[启动] 下载器启动，最大并发数: {self.max_concurrent}")

        # 创建工作线程
        self._workers = [
            asyncio.create_task(self._download_worker(), name=f"downloader-{i}")
            for i in range(self.max_concurrent)
        ]

    async def wait_until_complete(self) -> None:
        """等待所有下载任务完成"""
        await self.download_queue.join()
        await self._safe_print("[完成] 所有下载任务已完成")

    async def stop(self) -> None:
        """停止下载器"""
        self._is_running = False

        # 取消所有工作线程
        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

        # 关闭session
        if self._session and not self._session.closed:
            await self._session.close()

    async def _safe_print(self, message: str) -> None:
        """线程安全打印"""
        async with self.print_lock:
            print(message)

    def get_stats(self) -> dict:
        """获取下载统计信息"""
        return {
            "queue_size": self.download_queue.qsize(),
            "active_downloads": self.active_downloads,
            "completed_downloads": self.completed_downloads,
            "failed_downloads": len(self.failed_downloads),
            "is_running": self._is_running,
        }

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()
