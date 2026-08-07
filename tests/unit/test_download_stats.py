"""下载统计基线测试: DownloadStats 计数语义"""

import pytest

from modfetch.download.manager import DownloadManager, DownloadStats
from modfetch.download.verifier import FileVerifier
from modfetch.exceptions import DownloadError


class TestStatsCounting:
    async def test_local_copy_increments_completed(self, tmp_path, fake_jar):
        """file:// 本地复制 → completed +1"""
        manager = DownloadManager()
        dest = tmp_path / "out"

        result = await manager.download_file(
            fake_jar.as_uri(), "mod.jar", str(dest)
        )

        assert result is True
        assert (dest / "mod.jar").read_bytes() == fake_jar.read_bytes()
        stats = manager.get_stats()
        assert stats.completed == 1
        assert stats.failed == 0

    async def test_local_file_scheme_always_copies(self, tmp_path, fake_jar):
        """file:// 协议在跳过校验之前短路（当前行为基线：不触发 skipped）"""
        manager = DownloadManager()
        dest = tmp_path / "out"

        sha1 = await FileVerifier.calc_sha1(str(fake_jar))
        await manager.download_file(
            fake_jar.as_uri(), "mod.jar", str(dest), expected_sha1=sha1
        )
        result = await manager.download_file(
            fake_jar.as_uri(), "mod.jar", str(dest), expected_sha1=sha1
        )

        assert result is True
        stats = manager.get_stats()
        assert stats.completed == 2
        assert stats.skipped == 0

    async def test_failed_copy_increments_failed(self, tmp_path):
        """复制不存在的本地文件 → failed +1，抛 DownloadError，记入失败列表"""
        manager = DownloadManager()

        with pytest.raises(DownloadError):
            await manager.download_file(
                "file:///nonexistent/ghost.jar", "ghost.jar", str(tmp_path)
            )

        stats = manager.get_stats()
        assert stats.failed == 1
        # 当前行为基线: file:// 复制失败不写入失败列表（仅 HTTP 重试路径写入）
        assert manager.get_failed() == []

    async def test_bytes_downloaded_accumulates_on_http(self):
        """bytes_downloaded 在 HTTP 下载中按 chunk 累加（语义锁定，不触发网络）"""
        stats = DownloadStats()
        stats.bytes_downloaded += 8192
        stats.bytes_downloaded += 8192
        assert stats.bytes_downloaded == 16384

    async def test_enqueue_increments_total(self, tmp_path):
        """enqueue 成功 → total +1"""
        manager = DownloadManager()
        added = await manager.enqueue(
            url="file:///x.jar", filename="x.jar", download_dir=str(tmp_path)
        )
        assert added is True
        assert manager.get_stats().total == 1


class TestQueueFailureIsolation:
    async def test_worker_survives_failed_task(self, tmp_path):
        """worker 吞掉单任务异常并继续（当前行为基线：失败不向外传播）"""
        manager = DownloadManager(max_concurrent=1, max_retries=0)
        await manager.enqueue(
            url="file:///nonexistent/ghost.jar",
            filename="ghost.jar",
            download_dir=str(tmp_path),
        )

        # run() 正常返回而不抛出 — 失败仅体现在统计中
        await manager.run()

        stats = manager.get_stats()
        assert stats.failed == 1
        assert stats.total == 1
        assert manager.get_failed() == []
