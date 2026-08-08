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
from typing import Dict, Optional

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
    """纯下载执行器（实现 DownloaderPort）

    只负责"下载单个任务"，并发编排在 DownloadExecutor 层。
    关键设计：
    - 失败一律通过 DownloadResult(success=False) 返回，不抛异常
      （错误以值传递，符合项目约定，便于调用方统一决策）
    - 重试策略由注入的 RetryPolicy 决定，本类不内嵌重试逻辑
    - 下载先写 .part 临时文件，成功后 os.replace 原子替换，
      避免中断留下半成品文件被误认为完整
    """

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
        #: session 是否本类自建：为 True 时 close() 负责关闭，
        #: 外部注入的 session 生命周期归注入方管理。
        self._owned_session = session is None
        self._verify_ssl = verify_ssl
        #: 进程内 per-URL 互斥锁：同一 URL 并发请求只允许一次网络下载，
        #: 等待者在锁释放后重新校验缓存完整性（见 download 内 verify）。
        self._url_locks: Dict[str, asyncio.Lock] = {}

    @property
    def session(self) -> aiohttp.ClientSession:
        """懒加载 aiohttp session（首次访问才创建）

        延迟创建使仅构造不下载的场景不产生连接池开销；复用
        同一 session 以复用 TCP 连接。外部 session 已关闭时重建。
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def download(
        self,
        task: DownloadTask,
        progress: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """下载单个任务；失败返回 DownloadResult(success=False)

        Args:
            task: 下载任务（url/filename/destination/expected_sha1）
            progress: 进度回调 async (filename, downloaded, total)

        Returns:
            DownloadResult：成功/跳过时 success=True 并带 path 与
            字节数；失败时 success=False 并带 error/error_code/retries。

        流程：
        1. 校验目标路径安全（防目录穿越）
        2. file:// 协议走本地复制
        3. 已存在且校验通过 → 跳过（幂等，避免重复下载）
        4. 循环重试下载 + SHA1 校验，直至成功或耗尽重试次数
        """
        base = Path(task.destination)
        try:
            # safe_path 校验 filename 不越出 base 目录（防路径穿越）
            file_path = self._store.safe_path(base, task.filename)
        except ValueError as e:
            # 非法路径属于配置错误，直接失败返回，不进入重试
            return DownloadResult(
                success=False, filename=task.filename, error=str(e),
                error_code="E303",
            )

        # file:// 协议走本地复制（无需并发锁，本地 IO 幂等）
        if task.url.startswith("file://"):
            return await self._download_local(task, file_path)

        # 缓存键级互斥：同一 URL 只允许一个网络下载。
        # 等待者在锁释放后重新执行缓存校验（可能已被首个请求填充）。
        lock = self._url_lock(task.url)
        async with lock:
            return await self._download_http(task, file_path, progress)

    def _url_lock(self, url: str) -> asyncio.Lock:
        """获取 URL 对应的进程内互斥锁（惰性创建）"""
        lock = self._url_locks.get(url)
        if lock is None:
            lock = asyncio.Lock()
            self._url_locks[url] = lock
        return lock

    async def _download_http(
        self,
        task: DownloadTask,
        file_path: Path,
        progress: Optional[ProgressCallback],
    ) -> DownloadResult:
        """在锁内执行 HTTP 下载（含缓存命中预检与重试循环）

        锁语义：持锁期间才可发起网络请求；锁释放前先做一次幂等
        校验，等待者（已被锁阻挡）释放后重新校验缓存完整性。
        """
        # 已存在且校验通过 → 跳过（幂等优化：多 target/多 job 共享缓存）
        if await self._store.verify(file_path, self._hashes(task)):
            logger.info(f"[跳过] '{task.filename}' 已存在且校验通过")
            return DownloadResult(
                success=True, filename=task.filename, path=str(file_path),
                skipped=True,
            )

        logger.info(f"[开始] 下载: {task.filename}")

        # 重试循环：max_retries+1 次尝试（首次 + 重试次数）
        for attempt in range(self._retry.max_retries + 1):
            try:
                bytes_written = await self._download_once(
                    task, file_path, progress
                )

                # 校验文件：下载完成后核对 SHA1，防止拿到损坏/被篡改内容
                if not await self._store.verify(file_path, self._hashes(task)):
                    # 校验失败：删除不完整文件，抛校验错误进入重试
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
                # 无论何种失败，先清掉残留的 .part 与目标文件，
                # 避免下次重试时把旧内容误当新下载结果。
                file_path.unlink(missing_ok=True)
                file_path.with_name(file_path.name + ".part").unlink(
                    missing_ok=True
                )

                if self._retry.should_retry(e, attempt):
                    # 可重试错误（网络/校验）：按退避策略等待后重试
                    delay = self._retry.delay_for(attempt)
                    logger.warning(
                        f"[重试] 下载 '{task.filename}' 失败 "
                        f"(第 {attempt + 1} 次): {e}. {delay:.1f}s 后重试..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # 不可重试：把非 DownloadError 包装为 DownloadError，
                    # 统一以值传递错误，返回失败结果而非抛出。
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
        """单次下载尝试：.part 临时文件 → 原子替换

        Returns:
            写入的字节数

        Raises:
            DownloadNetworkError: HTTP 非 200

        设计说明：
        - 先写 ``<name>.part`` 临时文件，成功后 ``os.replace``
          原子替换为目标文件：即使进程中断，目标路径也不会出现
          半截文件，且 replace 在同一文件系统上是原子操作。
        - 进度回调异常单独捕获并忽略，不触发重试——进度回调只是
          旁路通知，其失败不应影响下载本身。
        """
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

            # Content-Length 可能缺失（分块传输），缺省按 0 处理，
            # 进度回调据此显示"未知总量"。
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            async def _stream():
                """把响应体包装为字节流，边下载边上报进度"""
                nonlocal downloaded
                # 8192 字节分块读取，兼顾内存占用与 IO 效率
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

            # 由 store 负责流式落盘（自动建父目录）
            written = await self._store.write(part_path, _stream())

        # 下载成功：原子替换 .part → 目标文件
        os.replace(part_path, file_path)
        return written

    async def _download_local(
        self, task: DownloadTask, file_path: Path
    ) -> DownloadResult:
        """file:// 协议本地复制

        本地文件无需走 HTTP，直接复制（支持文件与目录）。
        复制完成后按 task.expected_sha1 校验（与 HTTP 路径一致），
        防止本地源文件被篡改/损坏却仍被当作完整制品缓存。
        失败以 DownloadResult 返回，不抛异常。
        """
        try:
            # task.url[7:] 去掉 "file://" 前缀得到本地路径
            size = await self._copier.copy(task.url[7:], file_path)
        except DownloadError as e:
            logger.error(f"[错误] 复制文件失败: {e}")
            return DownloadResult(
                success=False, filename=task.filename,
                error=str(e), error_code=e.code,
            )

        # 目录复制（copytree）场景：SHA1 只对单一文件内容定义，
        # 无法对目录计算，且预期哈希仅出现在单文件制品上——跳过校验。
        if file_path.is_dir():
            logger.success(f"[完成] 本地目录复制完成: {task.filename}")
            return DownloadResult(
                success=True, filename=task.filename,
                path=str(file_path), bytes_downloaded=size,
            )

        # 单文件：校验 SHA1（无预期值视为通过），不匹配视为失败
        if not await self._store.verify(file_path, self._hashes(task)):
            # 清理残留文件，避免损坏制品被后续构建复用
            file_path.unlink(missing_ok=True)
            logger.error(f"[错误] 本地复制 SHA1 校验失败: {task.filename}")
            error = DownloadChecksumError(
                f"SHA1 校验失败: {task.filename}",
                context={
                    "file": task.filename,
                    "expected": task.expected_sha1 or "",
                },
            )
            return DownloadResult(
                success=False, filename=task.filename,
                error=str(error), error_code=error.code,
            )

        logger.success(f"[完成] 本地文件复制完成: {task.filename}")
        return DownloadResult(
            success=True, filename=task.filename,
            path=str(file_path), bytes_downloaded=size,
        )

    @staticmethod
    def _hashes(task: DownloadTask) -> dict:
        """提取任务中用于校验的哈希集合（仅 sha1，无则空）"""
        return {"sha1": task.expected_sha1} if task.expected_sha1 else {}

    async def close(self) -> None:
        """关闭自建的 session（外部注入的 session 不在此关闭）"""
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()
