"""下载适配器单元测试: RetryPolicy / FileArtifactStore / HttpDownloader / DownloadExecutor"""

import pytest

from modfetch.adapters.download import (
    DownloadExecutor,
    FileArtifactStore,
    HttpDownloader,
    RetryPolicy,
)
from modfetch.domain.errors import (
    DownloadChecksumError,
    DownloadError,
    DownloadNetworkError,
)
from modfetch.ports.downloader import DownloadTask


class TestRetryPolicy:
    def test_delay_exponential_backoff(self):
        policy = RetryPolicy(base_delay=1.0, backoff_multiplier=2.0)
        assert policy.delay_for(0) == 1.0
        assert policy.delay_for(1) == 2.0
        assert policy.delay_for(2) == 4.0

    def test_delay_capped(self):
        policy = RetryPolicy(base_delay=10.0, max_delay=15.0)
        assert policy.delay_for(5) == 15.0

    def test_network_error_retried(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(DownloadNetworkError("x"), 0) is True

    def test_checksum_error_retried(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(DownloadChecksumError("x"), 0) is True

    def test_unknown_error_not_retried(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(ValueError("x"), 0) is False

    def test_retry_exhausted(self):
        policy = RetryPolicy(max_retries=2)
        assert policy.should_retry(DownloadNetworkError("x"), 2) is False


class TestSafePath:
    def test_normal_filename(self, tmp_path):
        store = FileArtifactStore()
        assert store.safe_path(tmp_path, "a.jar") == (tmp_path / "a.jar").resolve()

    def test_subdirectory_filename(self, tmp_path):
        store = FileArtifactStore()
        resolved = store.safe_path(tmp_path, "mods/a.jar")
        assert resolved == (tmp_path / "mods" / "a.jar").resolve()

    def test_absolute_path_rejected(self, tmp_path):
        store = FileArtifactStore()
        with pytest.raises(ValueError, match="绝对路径"):
            store.safe_path(tmp_path, "/etc/passwd")

    def test_traversal_rejected(self, tmp_path):
        store = FileArtifactStore()
        with pytest.raises(ValueError, match="穿越"):
            store.safe_path(tmp_path, "../../etc/passwd")


@pytest.fixture
def downloader():
    return HttpDownloader(
        retry_policy=RetryPolicy(max_retries=0),
        artifact_store=FileArtifactStore(),
    )


class TestHttpDownloaderLocal:
    async def test_file_scheme_success(self, downloader, tmp_path, fake_jar):
        task = DownloadTask(
            url=fake_jar.as_uri(), filename="mod.jar",
            destination=str(tmp_path / "out"),
        )
        result = await downloader.download(task)

        assert result.success is True
        assert result.bytes_downloaded == fake_jar.stat().st_size
        assert (tmp_path / "out" / "mod.jar").exists()

    async def test_file_scheme_failure_result(self, downloader, tmp_path):
        """失败返回 DownloadResult(success=False) 而非抛异常或静默"""
        task = DownloadTask(
            url="file:///nonexistent/ghost.jar", filename="ghost.jar",
            destination=str(tmp_path),
        )
        result = await downloader.download(task)

        assert result.success is False
        assert result.error is not None
        assert result.error_code == "E300"

    async def test_path_traversal_rejected(self, downloader, tmp_path, fake_jar):
        task = DownloadTask(
            url=fake_jar.as_uri(), filename="../evil.jar",
            destination=str(tmp_path / "out"),
        )
        result = await downloader.download(task)

        assert result.success is False
        assert result.error_code == "E303"
        assert not (tmp_path / "evil.jar").exists()


class TestDownloadExecutor:
    async def test_mixed_outcomes_visible(self, downloader, tmp_path, fake_jar):
        """成功/失败任务都在报告中可见（旧 worker 吞异常的回归测试）"""
        executor = DownloadExecutor(downloader, max_concurrent=2)
        await executor.submit_many([
            DownloadTask(
                url=fake_jar.as_uri(), filename="good.jar",
                destination=str(tmp_path),
            ),
            DownloadTask(
                url="file:///nonexistent/ghost.jar", filename="ghost.jar",
                destination=str(tmp_path),
            ),
        ])

        report = await executor.run()

        assert report.total == 2
        assert report.completed == 1
        assert report.failed == 1
        assert report.failures[0].filename == "ghost.jar"

    async def test_task_status_lifecycle(self, downloader, tmp_path, fake_jar):
        executor = DownloadExecutor(downloader, max_concurrent=1)
        task = DownloadTask(
            url=fake_jar.as_uri(), filename="mod.jar",
            destination=str(tmp_path),
        )
        await executor.submit(task)
        assert executor.task_status(task) == "pending"

        await executor.run()
        assert executor.task_status(task) == "completed"

    async def test_failed_status(self, downloader, tmp_path):
        executor = DownloadExecutor(downloader, max_concurrent=1)
        task = DownloadTask(
            url="file:///nonexistent/x.jar", filename="x.jar",
            destination=str(tmp_path),
        )
        await executor.submit(task)
        await executor.run()
        assert executor.task_status(task) == "failed"

    async def test_dedup_same_task(self, downloader, tmp_path, fake_jar):
        """相同 (url, destination, filename) 的任务只入队一次"""
        executor = DownloadExecutor(downloader, max_concurrent=1)
        task = DownloadTask(
            url=fake_jar.as_uri(), filename="mod.jar",
            destination=str(tmp_path),
        )
        await executor.submit(task)
        await executor.submit(task)

        report = await executor.run()
        assert report.total == 1

    async def test_progress_callback_error_ignored(
        self, downloader, tmp_path, fake_jar
    ):
        """进度回调异常不影响下载结果，也不触发重试"""
        calls = []

        async def bad_progress(filename, downloaded, total):
            calls.append((filename, downloaded, total))
            raise RuntimeError("callback boom")

        executor = DownloadExecutor(
            downloader, max_concurrent=1, progress=bad_progress
        )
        await executor.submit(
            DownloadTask(
                url=fake_jar.as_uri(), filename="mod.jar",
                destination=str(tmp_path),
            )
        )
        report = await executor.run()

        assert report.completed == 1  # 下载成功
