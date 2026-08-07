"""CachingCatalog 单元测试

验证缓存装饰器的核心语义：
- 相同 key 重复查询只触发一次底层调用（project/version/loader）
- negative 结果（None）同样缓存，避免反复请求缺失项
- single-flight：并发同 key 请求合并为一次底层调用
- search 透传不缓存
- close/clear 生命周期行为
"""

import asyncio

import pytest

from modfetch.adapters.caching import CachingCatalog
from modfetch.domain import ProjectInfo, ProjectType, VersionInfo
from modfetch.domain.config_models import ModLoader

# -- 可计数的内存 catalog 桩 -------------------------------------------------


class CountingCatalog:
    """记录每次底层调用并可配置返回值的内存 CatalogPort 桩"""

    def __init__(self) -> None:
        self.project_calls = 0
        self.version_calls = 0
        self.loader_calls = 0
        self.search_calls = 0
        self.project_result: ProjectInfo | None = None
        self.version_result: tuple[VersionInfo | None, dict | None] = (None, None)
        self.loader_result: str | None = None
        self.search_result: list[ProjectInfo] = []
        self.closed = False

    def _make_project(self, pid: str) -> ProjectInfo:
        return ProjectInfo(
            id=pid,
            name=f"mod-{pid}",
            title=f"Mod {pid}",
            description="stub",
            project_type=ProjectType.MOD,
            versions=["v1"],
        )

    def _make_version(self, vid: str) -> VersionInfo:
        return VersionInfo(
            id=vid,
            name="1.0.0",
            version="1.0.0",
            loaders=[ModLoader.FABRIC],
            game_versions=["1.21.1"],
            files=[],
            dependencies=[],
        )

    async def get_project(self, identifier: str) -> ProjectInfo | None:
        self.project_calls += 1
        return self.project_result

    async def get_version(
        self,
        project_id: str,
        mc_version: str,
        loader: str,
        specific_version: str | None = None,
    ) -> tuple[VersionInfo | None, dict | None]:
        self.version_calls += 1
        return self.version_result

    async def get_loader_version(
        self, loader: str, mc_version: str
    ) -> str | None:
        self.loader_calls += 1
        return self.loader_result

    async def search(
        self,
        query: str,
        *,
        project_type: str | None = None,
        mc_version: str | None = None,
        loader: str | None = None,
        limit: int = 5,
    ) -> list[ProjectInfo]:
        self.search_calls += 1
        return self.search_result

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def counting() -> CountingCatalog:
    return CountingCatalog()


@pytest.fixture
def cached(counting: CountingCatalog) -> CachingCatalog:
    return CachingCatalog(counting)


class TestProjectCache:
    async def test_repeated_query_single_call(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """相同 identifier 重复查询 → 仅一次底层调用"""
        counting.project_result = counting._make_project("AAAA0001")
        await cached.get_project("AAAA0001")
        await cached.get_project("AAAA0001")
        await cached.get_project("AAAA0001")
        assert counting.project_calls == 1

    async def test_negative_result_cached(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """项目不存在（None）也缓存，避免反复请求缺失项"""
        counting.project_result = None
        assert await cached.get_project("GHOST") is None
        assert await cached.get_project("GHOST") is None
        assert counting.project_calls == 1

    async def test_different_identifier_uncached(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """不同 identifier 互不干扰（各自触发底层调用）"""
        counting.project_result = counting._make_project("X")
        await cached.get_project("AAA")
        await cached.get_project("BBB")
        assert counting.project_calls == 2


class TestVersionCache:
    async def test_repeated_query_single_call(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """相同 (project, mc, loader) 重复查询 → 仅一次底层调用"""
        counting.version_result = (counting._make_version("v1"), {"filename": "a.jar"})
        for _ in range(3):
            await cached.get_version("AAAA0001", "1.21.1", "fabric")
        assert counting.version_calls == 1

    async def test_key_includes_loader_and_specific_version(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """缓存键区分 loader 与 specific_version，不同组合各自查询"""
        counting.version_result = (counting._make_version("v1"), {"filename": "a.jar"})
        await cached.get_version("P", "1.21.1", "fabric")
        await cached.get_version("P", "1.21.1", "forge")
        await cached.get_version("P", "1.21.1", "fabric", "1.0.0")
        assert counting.version_calls == 3

    async def test_negative_result_cached(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """无匹配版本（None, None）也缓存"""
        counting.version_result = (None, None)
        assert await cached.get_version("P", "1.21.1", "fabric") == (None, None)
        assert await cached.get_version("P", "1.21.1", "fabric") == (None, None)
        assert counting.version_calls == 1


class TestLoaderVersionCache:
    async def test_repeated_query_single_call(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """相同 (loader, mc) 重复查询 → 仅一次底层调用"""
        counting.loader_result = "0.16.5"
        await cached.get_loader_version("fabric", "1.21.1")
        await cached.get_loader_version("fabric", "1.21.1")
        assert counting.loader_calls == 1

    async def test_negative_result_cached(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """loader 版本 None 也缓存（打包时不重复请求）"""
        counting.loader_result = None
        assert await cached.get_loader_version("forge", "1.21.1") is None
        assert await cached.get_loader_version("forge", "1.21.1") is None
        assert counting.loader_calls == 1


class TestSingleFlight:
    async def test_concurrent_same_key_single_call(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """并发同 key 请求合并为一次底层调用（single-flight）"""
        counting.project_result = counting._make_project("AAAA0001")

        # 让底层调用阻塞，保证并发窗口内所有协程都进入 await
        async def slow_get_project(identifier: str):
            counting.project_calls += 1
            await asyncio.sleep(0.05)
            return counting.project_result

        counting.get_project = slow_get_project  # type: ignore[method-assign]  # 测试桩替换

        results = await asyncio.gather(
            cached.get_project("AAAA0001"),
            cached.get_project("AAAA0001"),
            cached.get_project("AAAA0001"),
        )
        assert [r.id for r in results if r] == ["AAAA0001"] * 3
        assert counting.project_calls == 1


class TestPassthrough:
    async def test_search_not_cached(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """search 透传不缓存（每次触发底层）"""
        counting.search_result = [counting._make_project("X")]
        await cached.search("sodium")
        await cached.search("sodium")
        assert counting.search_calls == 2

    async def test_close_passthrough(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """close 透传给内层"""
        await cached.close()
        assert counting.closed

    async def test_clear_empties_cache(
        self, cached: CachingCatalog, counting: CountingCatalog
    ):
        """clear 后缓存清空，重新查询触发底层调用"""
        counting.project_result = counting._make_project("X")
        await cached.get_project("X")
        cached.clear()
        await cached.get_project("X")
        assert counting.project_calls == 2
        assert cached.project_cache_size == 1