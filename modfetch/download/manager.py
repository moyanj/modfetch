"""
下载管理器

整合下载功能，实现下载队列管理、并发控制、下载统计。
"""

import asyncio
import os
import shutil
from typing import Optional, Callable
from dataclasses import dataclass

import aiohttp
import aiofiles
from loguru import logger

from modfetch.download.queue import DownloadQueue, Priority
from modfetch.download.verifier import FileVerifier
from modfetch.exceptions import (
    DownloadError,
    DownloadNetworkError,
    DownloadChecksumError,
)


@dataclass
class DownloadStats:
    """下载统计"""

    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    bytes_downloaded: int = 0


class DownloadManager:
    """下载管理器"""

    def __init__(
        self,
        max_concurrent: int = 5,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        session: Optional[aiohttp.ClientSession] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ):
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.queue = DownloadQueue()
        self.verifier = FileVerifier()
        self.stats = DownloadStats()
        self._session = session
        self._owned_session = session is None
        self._progress_callback = progress_callback
        self._workers: list[asyncio.Task] = []

        self._failed_downloads: list[str] = []

    @property
    def session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def enqueue(
        self,
        url: str,
        filename: str,
        download_dir: str,
        sha1: Optional[str] = None,
        category: str = "files",
        priority: Priority = Priority.NORMAL,
    ) -> bool:
        """添加下载任务"""
        added = await self.queue.put(
            url=url,
            filename=filename,
            download_dir=download_dir,
            sha1=sha1,
            category=category,
            priority=priority,
        )
        if added:
            self.stats.total += 1
            logger.debug(f"[队列] {category} '{filename}' 已加入下载队列")
        return added

    async def download_file(
        self,
        url: str,
        filename: str,
        download_dir: str,
        expected_sha1: Optional[str] = None,
    ) -> bool:
        """
        下载单个文件

        Returns:
            True 如果下载成功，False 如果失败
        """
        file_path = os.path.join(download_dir, filename)

        # 确保目录存在
        os.makedirs(download_dir, exist_ok=True)

        # 处理本地文件
        if url.startswith("file://"):
            return await self._copy_local_file(url[7:], file_path)

        # 检查文件是否已存在且校验通过
        if await self.verifier.is_valid(file_path, expected_sha1):
            self.stats.skipped += 1
            logger.info(f"[跳过] '{filename}' 已存在且校验通过")
            return True

        logger.info(f"[开始] 下载: {filename}")

        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.get(url, ssl=False) as response:
                    if response.status != 200:
                        raise DownloadNetworkError(
                            f"HTTP {response.status}",
                            context={"url": url, "status": response.status},
                        )

                    total_size = int(response.headers.get("Content-Length", 0))
                    if attempt == 0:
                        logger.info(
                            f"[信息] 文件大小: {total_size / (1024 * 1024):.2f} MB"
                        )

                    async with aiofiles.open(file_path, "wb") as f:
                        downloaded = 0
                        last_percent = 0

                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            self.stats.bytes_downloaded += len(chunk)

                            # 进度回调
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if percent - last_percent >= 5:
                                    if self._progress_callback:
                                        self._progress_callback(filename, percent)
                                    logger.info(f"[进度] {filename}: {percent:.1f}%")
                                    last_percent = percent

                # 校验文件
                if expected_sha1 and not await self.verifier.verify_sha1(
                    file_path, expected_sha1
                ):
                    os.remove(file_path)
                    raise DownloadChecksumError(
                        f"SHA1 校验失败: {filename}",
                        context={"file": filename, "expected": expected_sha1},
                    )

                self.stats.completed += 1
                logger.success(f"[完成] '{filename}' 下载完成")
                return True

            except Exception as e:
                # 清理不完整的文件
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

                if attempt < self.max_retries:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        f"[重试] 下载 '{filename}' 失败 (第 {attempt + 1} 次): {e}. "
                        f"{delay:.1f}s 后重试..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self.stats.failed += 1
                    self._failed_downloads.append(filename)
                    logger.error(f"[错误] 下载 '{filename}' 最终失败: {e}")

                    if isinstance(e, DownloadError):
                        raise
                    raise DownloadError(
                        f"下载失败: {filename}", context={"error": str(e)}
                    )

        return False

    async def _copy_local_file(self, src_path: str, dest_path: str) -> bool:
        """复制本地文件"""
        logger.info(f"[复制] 本地文件: {os.path.basename(src_path)}")
        try:
            if os.path.isdir(src_path):
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
                shutil.copytree(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)
            self.stats.completed += 1
            logger.success(f"[完成] 本地文件复制完成: {os.path.basename(src_path)}")
            return True
        except Exception as e:
            self.stats.failed += 1
            logger.error(f"[错误] 复制文件失败: {e}")
            raise DownloadError(f"复制文件失败", context={"error": str(e)})

    async def _worker(self):
        """下载工作线程"""
        while True:
            try:
                task = await self.queue.get()

                try:
                    await self.download_file(
                        task.url,
                        task.filename,
                        task.download_dir,
                        task.sha1,
                    )
                finally:
                    self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception:
                # 工作线程不应该因为单个任务失败而退出
                pass

    async def start(self):
        """启动下载器"""
        logger.info(f"[启动] 下载器启动，最大并发数: {self.max_concurrent}")
        self._workers = [
            asyncio.create_task(self._worker(), name=f"downloader-{i}")
            for i in range(self.max_concurrent)
        ]

    async def wait_until_complete(self):
        """等待所有任务完成"""
        await self.queue.join()

    async def stop(self):
        """停止下载器"""
        logger.debug("[停止] 正在停止下载器...")
        # 取消所有工作线程
        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

        # 关闭 session
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()
        logger.debug("[停止] 下载器已停止")

    async def run(self):
        """运行下载器（启动并等待完成）"""
        await self.start()
        await self.wait_until_complete()
        await self.stop()

    def get_stats(self) -> DownloadStats:
        """获取下载统计"""
        return self.stats

    def get_failed(self) -> list[str]:
        """获取失败的下载列表"""
        return self._failed_downloads.copy()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()
