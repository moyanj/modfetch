"""ModrinthClient / build_modrinth_facets 单元测试（完全离线）

策略：不创建真实 aiohttp.ClientSession，注入伪 session（FakeSession），
其 get() 按预设顺序弹出 FakeResponse。这样可驱动 client 的真实
``_request``/``raw_get``/``_get_meta_loader_version``/``get_forge_version``
等网络出口，同时覆盖 session 懒加载与 close 生命周期。
"""

import json
from pathlib import Path
from typing import cast

import aiohttp
import pytest

from modfetch.adapters.modrinth import client as client_module
from modfetch.adapters.modrinth.client import MODRINTH_BASE_URL, ModrinthClient
from modfetch.adapters.modrinth.facets import build_modrinth_facets
from modfetch.domain.errors import APIError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "api_responses"


def _fixture(name: str) -> dict:
    """读取真实捕获的 Modrinth API 响应 fixture"""
    return json.loads((FIXTURES_DIR / name).read_text())


# -- 伪 aiohttp 层 -----------------------------------------------------------


class FakeResponse:
    """伪 aiohttp 响应：async context manager + status/url/json"""

    def __init__(
        self,
        status: int = 200,
        payload=None,
        url: str = f"{MODRINTH_BASE_URL}/x",
    ):
        self.status = status
        self._payload = payload
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload


class FakeSession:
    """记录调用并弹出预设响应的伪 session（不触网）

    aiohttp 的 ``session.get()`` 返回支持 ``async with`` 的请求对象
    而非协程，故这里用普通方法直接返回 FakeResponse。
    """

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []  # (url, kwargs)
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


class BoomSession:
    """get 直接抛异常的伪 session（模拟网络故障）"""

    def __init__(self):
        self.closed = False

    def get(self, url, **kwargs):
        raise aiohttp.ClientError("network down")

    async def close(self):
        self.closed = True


def make_client(responses=None) -> tuple[ModrinthClient, FakeSession]:
    """构造注入伪 session 的客户端，返回 (client, session)"""
    session = FakeSession(responses)
    # cast：测试桩鸭子类型满足 aiohttp.ClientSession 使用面，非真实实例
    return ModrinthClient(session=cast(aiohttp.ClientSession, session)), session


# -- facets 构造 --------------------------------------------------------------


class TestBuildModrinthFacets:
    def test_no_filters_returns_none(self):
        assert build_modrinth_facets() is None

    def test_all_filters_encoded(self):
        result = build_modrinth_facets(
            project_type="mod", mc_version="1.21.1", mod_loader="fabric"
        )
        assert result is not None
        assert json.loads(result) == [
            ["project_type:mod"],
            ["versions:1.21.1"],
            ["categories:fabric"],
        ]

    def test_project_type_only(self):
        result = build_modrinth_facets(project_type="shader")
        assert result is not None
        assert json.loads(result) == [
            ["project_type:shader"]
        ]

    def test_mc_version_only(self):
        result = build_modrinth_facets(mc_version="1.20.1")
        assert result is not None
        assert json.loads(result) == [
            ["versions:1.20.1"]
        ]

    def test_loader_only(self):
        result = build_modrinth_facets(mod_loader="forge")
        assert result is not None
        assert json.loads(result) == [
            ["categories:forge"]
        ]


# -- _request / raw_get ------------------------------------------------------


class TestRequest:
    async def test_200_returns_json(self):
        client, _ = make_client([FakeResponse(200, {"ok": 1})])
        assert await client._request(f"{MODRINTH_BASE_URL}/x") == {"ok": 1}

    async def test_404_returns_none(self):
        client, _ = make_client([FakeResponse(404)])
        assert await client._request(f"{MODRINTH_BASE_URL}/x") is None

    async def test_500_raises_api_error(self):
        client, _ = make_client([FakeResponse(500)])
        with pytest.raises(APIError) as excinfo:
            await client._request(f"{MODRINTH_BASE_URL}/x")
        assert excinfo.value.context["status_code"] == 500
        assert excinfo.value.context["url"] == f"{MODRINTH_BASE_URL}/x"

    async def test_429_raises_api_error(self):
        client, _ = make_client([FakeResponse(429)])
        with pytest.raises(APIError) as excinfo:
            await client._request(f"{MODRINTH_BASE_URL}/x")
        assert excinfo.value.context["status_code"] == 429

    async def test_params_forwarded(self):
        client, session = make_client([FakeResponse(200, {})])
        await client._request(f"{MODRINTH_BASE_URL}/x", params={"a": "1"})
        assert session.calls[0][1]["params"] == {"a": "1"}


class TestRawGet:
    async def test_200_returns_status_and_json(self):
        client, _ = make_client(
            [FakeResponse(200, {"data": 1}, url=f"{MODRINTH_BASE_URL}/project/x")]
        )
        status, payload = await client.raw_get("/project/x")
        assert (status, payload) == (200, {"data": 1})

    async def test_non_200_returns_status_none(self):
        client, _ = make_client(
            [FakeResponse(404, url=f"{MODRINTH_BASE_URL}/project/x")]
        )
        assert await client.raw_get("/project/x") == (404, None)

    async def test_url_joins_base(self):
        client, session = make_client([FakeResponse(200, {})])
        await client.raw_get("/project/x", params={"p": "1"})
        url, kwargs = session.calls[0]
        assert url == f"{MODRINTH_BASE_URL}/project/x"
        assert kwargs["params"] == {"p": "1"}


# -- get_project -------------------------------------------------------------


class TestGetProject:
    async def test_success_maps_project(self):
        client, session = make_client(
            [FakeResponse(200, _fixture("project_sodium.json"))]
        )
        project = await client.get_project("sodium")
        assert project is not None
        assert project.id == "AAAA0001"
        assert project.name == "sodium"
        assert project.title == "Sodium"
        assert project.project_type == "mod"
        assert project.versions == ["v0.6.0", "v0.5.8"]
        assert session.calls[0][0] == f"{MODRINTH_BASE_URL}/project/sodium"

    async def test_not_found_returns_none(self):
        client, _ = make_client([FakeResponse(404)])
        assert await client.get_project("ghost") is None


# -- search ------------------------------------------------------------------


class TestSearch:
    async def test_search_projects_with_filters_builds_facets(self):
        client, session = make_client(
            [FakeResponse(200, _fixture("search_sodium.json"))]
        )
        results = await client.search_projects(
            "sodium",
            project_type="mod",
            mc_version="1.21.1",
            mod_loader="fabric",
            limit=10,
        )
        assert len(results) == 1
        hit = results[0]
        assert hit.id == "AAAA0001"
        assert hit.name == "sodium"
        # downloads 由 mapper 动态 setattr 附加，非 ProjectInfo 静态字段
        assert getattr(hit, "downloads") == 30000000

        url, kwargs = session.calls[0]
        assert url == f"{MODRINTH_BASE_URL}/search"
        params = kwargs["params"]
        assert params["query"] == "sodium"
        assert params["limit"] == "10"
        assert json.loads(params["facets"]) == [
            ["project_type:mod"],
            ["versions:1.21.1"],
            ["categories:fabric"],
        ]

    async def test_search_without_filters_omits_facets(self):
        client, session = make_client(
            [FakeResponse(200, _fixture("search_sodium.json"))]
        )
        await client.search_projects("sodium")
        params = session.calls[0][1]["params"]
        assert "facets" not in params

    async def test_search_none_response_returns_empty(self):
        client, _ = make_client([FakeResponse(404)])
        assert await client.search_projects("ghost") == []

    async def test_search_empty_hits(self):
        client, _ = make_client([FakeResponse(200, {"hits": []})])
        assert await client.search_projects("nothing") == []

    async def test_search_alias_passes_loader(self):
        """CatalogPort 统一入口 search 把 loader 转发为 mod_loader"""
        client, session = make_client(
            [FakeResponse(200, _fixture("search_sodium.json"))]
        )
        await client.search("sodium", loader="fabric")
        params = session.calls[0][1]["params"]
        assert json.loads(params["facets"]) == [["categories:fabric"]]


# -- get_version -------------------------------------------------------------


class TestGetVersion:
    async def test_returns_latest_when_no_specific(self):
        client, session = make_client(
            [FakeResponse(200, [_fixture("version_sodium_1.21_fabric.json")])]
        )
        version, file_info = await client.get_version("sodium", "1.21.1", "fabric")
        assert version is not None
        assert version.id == "v0.6.0"
        assert version.version == "0.6.0"
        assert version.game_versions == ["1.21.1"]
        assert file_info is not None
        assert file_info["filename"] == "sodium-fabric-0.6.0.jar"

        url, kwargs = session.calls[0]
        assert url == f"{MODRINTH_BASE_URL}/project/sodium/version"
        assert kwargs["params"] == {
            "game_versions": '["1.21.1"]',
            "loaders": '["fabric"]',
        }

    async def test_no_loader_omits_loaders_param(self):
        client, session = make_client([FakeResponse(200, [])])
        await client.get_version("sodium", "1.21.1", "")
        _, kwargs = session.calls[0]
        assert "loaders" not in kwargs["params"]

    async def test_404_returns_none_none(self):
        client, _ = make_client([FakeResponse(404)])
        assert await client.get_version("sodium", "1.21.1", "fabric") == (None, None)

    async def test_empty_response_returns_none_none(self):
        client, _ = make_client([FakeResponse(200, [])])
        assert await client.get_version("sodium", "1.21.1", "fabric") == (None, None)

    async def test_specific_version_matches_id(self):
        client, _ = make_client(
            [FakeResponse(200, [_fixture("version_sodium_1.21_fabric.json")])]
        )
        version, file_info = await client.get_version(
            "sodium", "1.21.1", "fabric", specific_version="v0.6.0"
        )
        assert version is not None
        assert version.version == "0.6.0"
        assert file_info is not None

    async def test_specific_version_matches_number(self):
        client, _ = make_client(
            [FakeResponse(200, [_fixture("version_sodium_1.21_fabric.json")])]
        )
        version, _ = await client.get_version(
            "sodium", "1.21.1", "fabric", specific_version="0.6.0"
        )
        assert version is not None
        assert version.version == "0.6.0"

    async def test_specific_version_no_match_no_fallback(self):
        """指定版本未命中 → (None, None)，刻意不降级到最新版"""
        client, _ = make_client(
            [FakeResponse(200, [_fixture("version_sodium_1.21_fabric.json")])]
        )
        assert await client.get_version(
            "sodium", "1.21.1", "fabric", specific_version="9.9.9"
        ) == (None, None)

    async def test_picks_primary_file(self):
        """多文件时优先 primary 标记的文件"""
        version = _fixture("version_sodium_1.21_fabric.json")
        version["files"] = [
            {
                "url": "https://cdn.example.com/secondary.jar",
                "filename": "secondary.jar",
                "size": 1,
                "primary": False,
            },
            {
                "url": "https://cdn.example.com/primary.jar",
                "filename": "primary.jar",
                "size": 2,
                "primary": True,
            },
        ]
        client, _ = make_client([FakeResponse(200, [version])])
        _, file_info = await client.get_version("sodium", "1.21.1", "fabric")
        assert file_info is not None
        assert file_info["filename"] == "primary.jar"

    async def test_no_primary_falls_back_to_first(self):
        """无 primary 标记时退化为取第一个文件"""
        version = _fixture("version_sodium_1.21_fabric.json")
        version["files"] = [
            {
                "url": "https://cdn.example.com/a.jar",
                "filename": "a.jar",
                "size": 1,
                "primary": False,
            },
            {
                "url": "https://cdn.example.com/b.jar",
                "filename": "b.jar",
                "size": 2,
                "primary": False,
            },
        ]
        client, _ = make_client([FakeResponse(200, [version])])
        _, file_info = await client.get_version("sodium", "1.21.1", "fabric")
        assert file_info is not None
        assert file_info["filename"] == "a.jar"

    async def test_no_files_returns_none_file(self):
        """版本无文件 → file_info 为 None"""
        version = _fixture("version_sodium_1.21_fabric.json")
        version["files"] = []
        client, _ = make_client([FakeResponse(200, [version])])
        version_info, file_info = await client.get_version(
            "sodium", "1.21.1", "fabric"
        )
        assert version_info is not None
        assert file_info is None


# -- 加载器版本 ---------------------------------------------------------------


class TestLoaderVersion:
    async def test_fabric_dispatch(self):
        client, session = make_client(
            [FakeResponse(200, [{"loader": {"version": "0.16.5"}}])]
        )
        assert await client.get_loader_version("fabric", "1.21.1") == "0.16.5"
        assert session.calls[0][0] == (
            "https://meta.fabricmc.net/v2/versions/loader/1.21.1"
        )

    async def test_quilt_dispatch(self):
        client, session = make_client(
            [FakeResponse(200, [{"loader": {"version": "0.27.0"}}])]
        )
        assert await client.get_loader_version("quilt", "1.20.1") == "0.27.0"
        assert session.calls[0][0] == (
            "https://meta.quiltmc.org/v3/versions/loader/1.20.1"
        )

    async def test_forge_dispatch(self):
        client, session = make_client(
            [FakeResponse(200, {"1.21.1": ["50", "51", "52.0.1"]})]
        )
        assert await client.get_loader_version("forge", "1.21.1") == "52.0.1"
        assert session.calls[0][0] == (
            "https://files.minecraftforge.net/net/minecraftforge/forge/"
            "maven-metadata.json"
        )

    async def test_unsupported_loader_returns_none(self):
        client, session = make_client()
        assert await client.get_loader_version("neoforge", "1.21.1") is None
        assert session.calls == []


class TestMetaLoaderVersion:
    async def test_returns_first_loader_version(self):
        client, _ = make_client(
            [FakeResponse(200, [{"loader": {"version": "0.16.5"}}, {"loader": {"version": "0.15.0"}}])]
        )
        assert await client.get_fabric_version("1.21.1") == "0.16.5"

    async def test_empty_list_returns_none(self):
        client, _ = make_client([FakeResponse(200, [])])
        assert await client.get_fabric_version("1.21.1") is None

    async def test_non_200_returns_none(self):
        client, _ = make_client([FakeResponse(500)])
        assert await client.get_fabric_version("1.21.1") is None

    async def test_network_error_returns_none(self):
        client = ModrinthClient(session=cast(aiohttp.ClientSession, BoomSession()))
        assert await client.get_fabric_version("1.21.1") is None

    async def test_quilt_legacy_alias(self):
        client, _ = make_client(
            [FakeResponse(200, [{"loader": {"version": "0.27.0"}}])]
        )
        assert await client.get_quilt_version("1.20.1") == "0.27.0"


class TestForgeVersion:
    async def test_returns_latest_build(self):
        client, _ = make_client([FakeResponse(200, {"1.21.1": ["50", "51", "52.0.1"]})])
        assert await client.get_forge_version("1.21.1") == "52.0.1"

    async def test_mc_version_missing_returns_none(self):
        client, _ = make_client([FakeResponse(200, {"1.20.4": ["1"]})])
        assert await client.get_forge_version("1.21.1") is None

    async def test_empty_build_list_returns_none(self):
        client, _ = make_client([FakeResponse(200, {"1.21.1": []})])
        assert await client.get_forge_version("1.21.1") is None

    async def test_non_200_returns_none(self):
        client, _ = make_client([FakeResponse(503)])
        assert await client.get_forge_version("1.21.1") is None

    async def test_network_error_returns_none(self):
        client = ModrinthClient(session=cast(aiohttp.ClientSession, BoomSession()))
        assert await client.get_forge_version("1.21.1") is None


# -- session 生命周期与 close -------------------------------------------------


class TestSessionLifecycle:
    def test_lazy_creates_session(self, monkeypatch):
        fake = FakeSession()
        monkeypatch.setattr(client_module.aiohttp, "ClientSession", lambda *a, **k: fake)
        client = ModrinthClient()
        assert client.session is fake
        assert client._owned_session is True

    def test_reuses_injected_session(self):
        fake = FakeSession()
        client = ModrinthClient(session=cast(aiohttp.ClientSession, fake))
        assert client.session is fake
        assert client._owned_session is False

    def test_recreates_when_injected_closed(self, monkeypatch):
        old = FakeSession()
        old.closed = True
        new = FakeSession()
        monkeypatch.setattr(client_module.aiohttp, "ClientSession", lambda *a, **k: new)
        client = ModrinthClient(session=cast(aiohttp.ClientSession, old))
        assert client.session is new


class TestClose:
    async def test_close_owned_session(self, monkeypatch):
        fake = FakeSession()
        monkeypatch.setattr(client_module.aiohttp, "ClientSession", lambda *a, **k: fake)
        client = ModrinthClient()
        assert client.session is fake  # 触发懒创建
        await client.close()
        assert fake.closed is True

    async def test_close_does_not_close_injected(self):
        fake = FakeSession()
        client = ModrinthClient(session=cast(aiohttp.ClientSession, fake))
        await client.close()
        assert fake.closed is False

    async def test_close_without_session_noop(self):
        client = ModrinthClient()
        await client.close()  # 不应抛异常

    async def test_async_context_manager(self, monkeypatch):
        fake = FakeSession()
        monkeypatch.setattr(client_module.aiohttp, "ClientSession", lambda *a, **k: fake)
        async with ModrinthClient() as client:
            assert client.session is fake  # 触发懒创建
        assert fake.closed is True