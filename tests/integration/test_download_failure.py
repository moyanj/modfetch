"""下载失败路径基线测试

锁定当前行为:
- download_file 最终失败 → 抛 DownloadError，stats.failed +1
- 队列 worker 吞掉失败异常 → run() 不抛出，失败仅在统计中体现
"""

import pytest

from modfetch.download.manager import DownloadManager
from modfetch.exceptions import DownloadError


class TestDirectDownloadFailure:
    async def test_missing_local_file_raises(self, tmp_path):
        manager = DownloadManager(max_retries=0)
        with pytest.raises(DownloadError) as exc_info:
            await manager.download_file(
                "file:///nonexistent/ghost.jar", "ghost.jar", str(tmp_path)
            )
        assert exc_info.value.code == "E300"
        assert manager.get_stats().failed == 1

    async def test_failure_leaves_no_partial_file(self, tmp_path):
        """失败后目标路径不产生残留文件"""
        manager = DownloadManager(max_retries=0)
        with pytest.raises(DownloadError):
            await manager.download_file(
                "file:///nonexistent/ghost.jar", "ghost.jar", str(tmp_path)
            )
        assert not (tmp_path / "ghost.jar").exists()


class TestQueuedDownloadFailure:
    async def test_run_completes_despite_failures(self, tmp_path, fake_jar):
        """混合成功/失败任务: run() 正常返回，统计分别计数"""
        manager = DownloadManager(max_concurrent=2, max_retries=0)
        await manager.enqueue(
            url=fake_jar.as_uri(), filename="good.jar", download_dir=str(tmp_path)
        )
        await manager.enqueue(
            url="file:///nonexistent/ghost.jar",
            filename="ghost.jar",
            download_dir=str(tmp_path),
        )

        await manager.run()

        stats = manager.get_stats()
        assert stats.total == 2
        assert stats.completed == 1
        assert stats.failed == 1
        # 当前行为基线: file:// 复制失败不写入失败列表（仅 HTTP 重试路径写入）
        assert manager.get_failed() == []
        assert (tmp_path / "good.jar").exists()

    async def test_stats_reflect_final_task_outcome(self, tmp_path):
        """失败任务的最终状态可通过统计与失败列表推断"""
        manager = DownloadManager(max_concurrent=1, max_retries=0)
        await manager.enqueue(
            url="file:///nonexistent/a.jar",
            filename="a.jar",
            download_dir=str(tmp_path),
        )
        await manager.enqueue(
            url="file:///nonexistent/b.jar",
            filename="b.jar",
            download_dir=str(tmp_path),
        )
        await manager.run()

        assert manager.get_stats().failed == 2
        # 当前行为基线: file:// 失败不写入失败列表
        assert manager.get_failed() == []
