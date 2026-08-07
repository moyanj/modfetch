"""
HTTP 下载器（DownloaderPort 实现）

职责单一的下载执行器:
- 重试逻辑集中在 RetryPolicy
- 失败通过 DownloadResult 返回（不静默吞没）
- .part 临时文件 → 成功后原子替换
- 文件路径经 ArtifactStorePort.safe_path 校验
- 进度回调异常不触发重试（单独捕获）
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import aiohttp
from loguru import logger

from modfetch.adapters.download.local_copier import LocalFileCopier
from modfetch.adapters.download.retry import RetryPolicy
from modfetch.domain.errors import (
    DownloadChecksumError,
    DownloadError,
    DownloadNetworkError,
)
from modfetch.ports.artifact_store import ArtifactStorePort
from modfetch.ports.downloader import (
    DownloadResult,
    DownloadTask,
    ProgressCallback,
)


class HttpDownloader:
    """纯下载执行器（实现 DownloaderPort）"""

    def __init__(
        self,
        retry_policy: RetryPolicy,
        artifact_store: ArtifactStorePort,
        local_copier: Optional[LocalFileCopier] = None,
        session: Optional[aiohttp.ClientSession] = None,
        verify_ssl: bool = True,
    ):
        self._retry = retry_policy
        self._store = artifact_store
        self._copier = local_copier or LocalFileCopier()
        self._session = session
        self._owned_session = session is None
        self._verify_ssl = verify_ssl

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def download(
        self,
        task: DownloadTask,
        progress: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """下载单个任务；失败返回 DownloadResult(success=False)"""
        base = Path(task.destination)
        try:
            file_path = self._store.safe_path(base, task.filename)
        except ValueError as e:
            return DownloadResult(
                success=False, filename=task.filename, error=str(e),
                error_code="E303",
            )

        # file:// 协议走本地复制
        if task.url.startswith("file://"):
            return await self._download_local(task, file_path)

        # 已存在且校验通过 → 跳过
        if await self._store.verify(file_path, self._hashes(task)):
            logger.info(f"[跳过] '{task.filename}' 已存在且校验通过")
            return DownloadResult(
                success=True, filename=task.filename, path=str(file_path),
                skipped=True,
            )

        logger.info(f"[开始] 下载: {task.filename}")

        for attempt in range(self._retry.max_retries + 1):
            try:
                bytes_written = await self._download_once(
                    task, file_path, progress
                )

                # 校验文件
                if not await self._store.verify(file_path, self._hashes(task)):
                    file_path.unlink(missing_ok=True)
                    raise DownloadChecksumError(
                        f"SHA1 校验失败: {task.filename}",
                        context={
                            "file": task.filename,
                            "expected": task.expected_sha1 or "",
                        },
                    )

                logger.success(f"[完成] '{task.filename}' 下载完成")
                return DownloadResult(
                    success=True,
                    filename=task.filename,
                    path=str(file_path),
                    bytes_downloaded=bytes_written,
                    retries=attempt,
                )

            except Exception as e:
                # 清理不完整文件（含 .part）
                file_path.unlink(missing_ok=True)
                file_path.with_name(file_path.name + ".part").unlink(
                    missing_ok=True
                )

                if self._retry.should_retry(e, attempt):
                    delay = self._retry.delay_for(attempt)
                    logger.warning(
                        f"[重试] 下载 '{task.filename}' 失败 "
                        f"(第 {attempt + 1} 次): {e}. {delay:.1f}s 后重试..."
                    )
                    await asyncio.sleep(delay)
                else:
                    error = e if isinstance(e, DownloadError) else DownloadError(
                        f"下载失败: {task.filename}", context={"error": str(e)}
                    )
                    logger.error(f"[错误] 下载 '{task.filename}' 最终失败: {e}")
                    return DownloadResult(
                        success=False,
                        filename=task.filename,
                        error=str(error),
                        error_code=error.code,
                        retries=attempt,
                    )

        # 不可达（max_retries+1 次循环必然返回），防御性返回
        return DownloadResult(
            success=False, filename=task.filename, error="超出重试次数",
            error_code="E300", retries=self._retry.max_retries,
        )

    async def _download_once(
        self,
        task: DownloadTask,
        file_path: Path,
        progress: Optional[ProgressCallback],
    ) -> int:
        """单次下载尝试：.part 临时文件 → 原子替换"""
        part_path = file_path.with_name(file_path.name + ".part")
        part_path.parent.mkdir(parents=True, exist_ok=True)

        async with self.session.get(
            task.url, ssl=self._verify_ssl
        ) as response:
            if response.status != 200:
                raise DownloadNetworkError(
                    f"HTTP {response.status}",
                    context={"url": task.url, "status": response.status},
                )

            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            async def _stream():
                nonlocal downloaded
                async for chunk in response.content.iter_chunked(8192):
                    downloaded += len(chunk)
                    # 进度回调异常不触发重试 — 单独捕获
                    if progress is not None:
                        try:
                            await progress(task.filename, downloaded, total_size)
                        except Exception as cb_err:
                            logger.warning(
                                f"进度回调异常（忽略）: {cb_err}"
                            )
                    yield chunk

            written = await self._store.write(part_path, _stream())

        os.replace(part_path, file_path)
        return written

    async def _download_local(
        self, task: DownloadTask, file_path: Path
    ) -> DownloadResult:
        """file:// 协议本地复制"""
        try:
            size = await self._copier.copy(task.url[7:], file_path)
            logger.success(f"[完成] 本地文件复制完成: {task.filename}")
            return DownloadResult(
                success=True, filename=task.filename,
                path=str(file_path), bytes_downloaded=size,
            )
        except DownloadError as e:
            logger.error(f"[错误] 复制文件失败: {e}")
            return DownloadResult(
                success=False, filename=task.filename,
                error=str(e), error_code=e.code,
            )

    @staticmethod
    def _hashes(task: DownloadTask) -> dict:
        return {"sha1": task.expected_sha1} if task.expected_sha1 else {}

    async def close(self) -> None:
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()
