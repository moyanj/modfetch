"""HttpDownloader HTTP 路径单元测试（完全离线）

策略：注入伪 aiohttp session（FakeSession），其 ``get`` 返回支持
``async with`` 的 FakeResponse（status/chunks/headers）。覆盖：
- 成功下载（含 sha1 校验、进度回调、Content-Length 缺失）
- 缓存命中跳过（幂等）
- 重试集成：网络错误/校验错误重试后成功、重试耗尽
- 非可重试异常包装为 DownloadError（E300）
- session 懒创建 / close 生命周期 / URL 互斥锁
"""

import hashlib
from typing import cast

import aiohttp
import pytest

from modfetch.adapters.download import http_downloader as downloader_module
from modfetch.adapters.download.file_store import FileArtifactStore
from modfetch.adapters.download.http_downloader import HttpDownloader
from modfetch.adapters.download.retry import RetryPolicy
from modfetch.ports.downloader import DownloadTask


class _FakeContent:
    """伪响应体：iter_chunked 产出预设分块；可配置迭代时抛异常"""

    def __init__(self, chunks=(), raise_on_iter=False):
        self._chunks = list(chunks)
        self._raise_on_iter = raise_on_iter

    async def iter_chunked(self, size):
        if self._raise_on_iter:
            if False:  # 使函数成为 async generator（语法需要）
                yield b""
            raise ValueError("boom")
        for chunk in self._chunks:
            yield chunk


class FakeResponse:
    """伪 aiohttp 响应：async context manager / status / headers / content"""

    def __init__(
        self,
        status: int = 200,
        chunks=(),
        headers=None,
        url: str = "https://cdn.example.com/x.jar",
    ):
        self.status = status
        self.headers = dict(headers or {})
        self.url = url
        self.content = _FakeContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """记录调用并弹出预设响应的伪 session（不触网）"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


class RaisingSession:
    """get 直接抛异常的伪 session（模拟连接超时/网络故障）"""

    def __init__(self):
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        raise TimeoutError("connection timeout")

    async def close(self):
        self.closed = True


def make_downloader(
    session,
    *,
    max_retries: int = 0,
    base_delay: float = 0.0,
    store=None,
) -> HttpDownloader:
    """构造注入伪 session 的下载器（退避置 0 保证测试快速）"""
    return HttpDownloader(
        retry_policy=RetryPolicy(max_retries=max_retries, base_delay=base_delay),
        artifact_store=store or FileArtifactStore(),
        # 测试桩满足 aiohttp.ClientSession 使用面，非真实实例
        session=cast(aiohttp.ClientSession, session),
    )


def make_task(tmp_path, filename="mod.jar", **overrides) -> DownloadTask:
    return DownloadTask(
        url="https://cdn.example.com/mod.jar",
        filename=filename,
        destination=str(tmp_path),
        **overrides,
    )


class TestHttpDownloadSuccess:
    async def test_success_writes_file(self, tmp_path):
        session = FakeSession([FakeResponse(200, chunks=[b"hello ", b"world"])])
        downloader = make_downloader(session)
        result = await downloader.download(make_task(tmp_path))

        assert result.success is True
        assert result.bytes_downloaded == 11
        assert result.retries == 0
        assert (tmp_path / "mod.jar").read_bytes() == b"hello world"
        # ssl 参数按 verify_ssl 默认值透传
        assert session.calls[0][1]["ssl"] is True

    async def test_success_with_sha1(self, tmp_path):
        content = b"verified-content"
        session = FakeSession([FakeResponse(200, chunks=[content])])
        downloader = make_downloader(session)
        result = await downloader.download(
            make_task(tmp_path, expected_sha1=hashlib.sha1(content).hexdigest())
        )
        assert result.success is True
        assert result.bytes_downloaded == len(content)

    async def test_skipped_when_cached(self, tmp_path):
        """目标已存在且校验通过 → 跳过，不发起网络请求"""
        content = b"cached-content"
        (tmp_path / "mod.jar").write_bytes(content)
        session = FakeSession([])  # 不应消费任何响应
        downloader = make_downloader(session)
        result = await downloader.download(
            make_task(tmp_path, expected_sha1=hashlib.sha1(content).hexdigest())
        )
        assert result.success is True
        assert result.skipped is True
        assert session.calls == []

    async def test_verify_ssl_false_passed(self, tmp_path):
        session = FakeSession([FakeResponse(200, chunks=[b"x"])])
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(max_retries=0),
            artifact_store=FileArtifactStore(),
            session=cast(aiohttp.ClientSession, session),
            verify_ssl=False,
        )
        await downloader.download(make_task(tmp_path))
        assert session.calls[0][1]["ssl"] is False


class TestHttpDownloadRetry:
    async def test_network_error_retries_then_success(self, tmp_path):
        """500 → 重试 → 200 成功，retries=1"""
        session = FakeSession(
            [
                FakeResponse(500),
                FakeResponse(200, chunks=[b"ok"]),
            ]
        )
        downloader = make_downloader(session, max_retries=1)
        result = await downloader.download(make_task(tmp_path))
        assert result.success is True
        assert result.retries == 1
        assert (tmp_path / "mod.jar").read_bytes() == b"ok"

    async def test_network_error_exhausted(self, tmp_path):
        """max_retries=0 → 首次失败即返回 E301"""
        session = FakeSession([FakeResponse(500)])
        downloader = make_downloader(session, max_retries=0)
        result = await downloader.download(make_task(tmp_path))
        assert result.success is False
        assert result.error_code == "E301"
        assert result.retries == 0
        assert not (tmp_path / "mod.jar").exists()

    async def test_checksum_error_retries_then_success(self, tmp_path):
        """首次内容与 sha1 不符 → 清理重试 → 二次内容正确 → 成功"""
        good = b"CORRECT"
        session = FakeSession(
            [
                FakeResponse(200, chunks=[b"WRONG"]),
                FakeResponse(200, chunks=[good]),
            ]
        )
        downloader = make_downloader(session, max_retries=1)
        result = await downloader.download(
            make_task(tmp_path, expected_sha1=hashlib.sha1(good).hexdigest())
        )
        assert result.success is True
        assert result.retries == 1
        assert (tmp_path / "mod.jar").read_bytes() == good

    async def test_checksum_error_exhausted(self, tmp_path):
        """校验失败且无重试 → E302，残留文件被清理"""
        session = FakeSession([FakeResponse(200, chunks=[b"WRONG"])])
        downloader = make_downloader(session, max_retries=0)
        result = await downloader.download(
            make_task(tmp_path, expected_sha1=hashlib.sha1(b"GOOD").hexdigest())
        )
        assert result.success is False
        assert result.error_code == "E302"
        assert not (tmp_path / "mod.jar").exists()

    async def test_unexpected_exception_not_retried(self, tmp_path):
        """流式读取抛非重试异常 → 不重试，包装为 E300"""
        resp = FakeResponse(200, chunks=[])
        resp.content = _FakeContent(raise_on_iter=True)
        session = FakeSession([resp])
        downloader = make_downloader(session, max_retries=2)
        result = await downloader.download(make_task(tmp_path))
        assert result.success is False
        assert result.error_code == "E300"
        assert result.retries == 0
        assert not (tmp_path / "mod.jar").exists()

    async def test_timeout_returns_failure(self, tmp_path):
        """session.get 抛超时 → 返回失败结果而非崩溃（当前不重试）"""
        session = RaisingSession()
        downloader = make_downloader(session, max_retries=2)
        result = await downloader.download(make_task(tmp_path))
        assert result.success is False
        assert result.error_code == "E300"
        assert result.error is not None


class TestHttpDownloadProgress:
    async def test_progress_reports_incremental(self, tmp_path):
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    chunks=[b"hello ", b"world"],
                    headers={"Content-Length": "11"},
                )
            ]
        )
        downloader = make_downloader(session)
        calls = []

        async def progress(filename, downloaded, total):
            calls.append((filename, downloaded, total))

        result = await downloader.download(make_task(tmp_path), progress=progress)
        assert result.success is True
        assert calls == [("mod.jar", 6, 11), ("mod.jar", 11, 11)]

    async def test_missing_content_length_total_zero(self, tmp_path):
        """无 Content-Length（分块传输）→ 进度 total 为 0"""
        session = FakeSession([FakeResponse(200, chunks=[b"abc"])])
        downloader = make_downloader(session)
        totals = []

        async def progress(filename, downloaded, total):
            totals.append(total)

        await downloader.download(make_task(tmp_path), progress=progress)
        assert totals == [0]

    async def test_progress_callback_error_ignored(self, tmp_path):
        """进度回调异常被单独捕获，不影响下载结果"""
        session = FakeSession([FakeResponse(200, chunks=[b"data"])])
        downloader = make_downloader(session)

        async def bad_progress(filename, downloaded, total):
            raise RuntimeError("callback boom")

        result = await downloader.download(make_task(tmp_path), progress=bad_progress)
        assert result.success is True
        assert result.bytes_downloaded == 4


class TestHttpDownloaderLifecycle:
    async def test_session_lazy_creates(self, monkeypatch):
        fake = FakeSession()
        monkeypatch.setattr(downloader_module.aiohttp, "ClientSession", lambda *a, **k: fake)
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(), artifact_store=FileArtifactStore()
        )
        assert downloader.session is fake
        assert downloader._owned_session is True

    async def test_session_recreated_when_injected_closed(self, monkeypatch):
        old = FakeSession()
        old.closed = True
        new = FakeSession()
        monkeypatch.setattr(downloader_module.aiohttp, "ClientSession", lambda *a, **k: new)
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(),
            artifact_store=FileArtifactStore(),
            session=cast(aiohttp.ClientSession, old),
        )
        assert downloader.session is new

    async def test_close_owned_session(self, monkeypatch):
        fake = FakeSession()
        monkeypatch.setattr(downloader_module.aiohttp, "ClientSession", lambda *a, **k: fake)
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(), artifact_store=FileArtifactStore()
        )
        assert downloader.session is fake  # 触发懒创建
        await downloader.close()
        assert fake.closed is True

    async def test_close_does_not_close_injected(self):
        fake = FakeSession()
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(),
            artifact_store=FileArtifactStore(),
            session=cast(aiohttp.ClientSession, fake),
        )
        await downloader.close()
        assert fake.closed is False

    async def test_close_without_session_noop(self):
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(), artifact_store=FileArtifactStore()
        )
        await downloader.close()  # 不应抛异常


class TestUrlLock:
    async def test_same_url_shared_lock(self):
        downloader = HttpDownloader(
            retry_policy=RetryPolicy(), artifact_store=FileArtifactStore()
        )
        lock1 = downloader._url_lock("https://a/x.jar")
        lock2 = downloader._url_lock("https://a/x.jar")
        lock3 = downloader._url_lock("https://b/y.jar")
        assert lock1 is lock2
        assert lock1 is not lock3


class TestHashes:
    async def test_with_expected_sha1(self):
        task = DownloadTask(
            url="x", filename="a.jar", destination="/tmp", expected_sha1="abc"
        )
        assert HttpDownloader._hashes(task) == {"sha1": "abc"}

    async def test_without_expected_sha1(self):
        task = DownloadTask(url="x", filename="a.jar", destination="/tmp")
        assert HttpDownloader._hashes(task) == {}