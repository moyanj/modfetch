"""
server 层测试公共 fixtures

- FakeCatalog: 离线 catalog 桩（raw_get 代理 + 远程校验查询方法）
- app: 经 create_app 构建的 FastAPI 实例（catalog 替换为 FakeCatalog）
- client: FastAPI TestClient（进入上下文触发 startup/shutdown 生命周期）

设计说明：routes.py 的代理路由（/api/search、/api/projects、/api/minecraft/*）
走 catalog.raw_get；/api/config/validate 与 /api/jobs 的远程校验走
catalog.get_project/get_version/search。FakeCatalog 同时实现两类接口，
使全部 server 测试完全离线且确定性可控。
"""

from __future__ import annotations

from typing import Optional

import pytest
from fastapi.testclient import TestClient

from modfetch.domain.models import ProjectInfo, ProjectType, VersionInfo


class FakeCatalog:
    """离线 catalog 桩

    职责：
    - raw_get: 供代理路由使用，按预设响应表返回 (status, data)
    - get_project/get_version/search: 供远程校验使用，按注册的项目返回
    """

    def __init__(self) -> None:
        self.raw_responses: dict[str, tuple[int, object]] = {}
        self.projects: dict[str, ProjectInfo] = {}
        self.versions: dict[tuple[str, str, str], tuple[VersionInfo, dict]] = {}
        self.raw_calls: list[tuple[str, Optional[dict]]] = []
        self.closed = False
        self.raise_on_raw = False

    def set_raw(self, path: str, status: int, data: object) -> None:
        """预设 raw_get 响应（path 为完整路径，如 /search）"""
        self.raw_responses[path] = (status, data)

    def add_project(self, project_id: str, slug: str) -> None:
        """注册一个可通过 slug/id 寻址的 mod 项目（含 1.21.1/fabric 版本）"""
        project = ProjectInfo(
            id=project_id,
            name=slug,
            title=slug.title(),
            description=f"stub {slug}",
            project_type=ProjectType.MOD,
            versions=["v1"],
        )
        self.projects[slug] = project
        self.projects[project_id] = project
        version = VersionInfo(
            id=f"{project_id}-v1",
            name=f"{slug} 1.0",
            version="1.0",
            loaders=[],
            game_versions=["1.21.1"],
            files=[],
            dependencies=[],
        )
        file_info = {
            "url": f"file:///stub/{slug}.jar",
            "filename": f"{slug}.jar",
            "size": 1,
            "hashes": {"sha1": "0" * 40},
        }
        self.versions[(project_id, "1.21.1", "fabric")] = (version, file_info)

    async def raw_get(self, path: str, params: Optional[dict] = None):
        """记录调用并返回预设响应；raise_on_raw 时抛异常（模拟网络故障）"""
        self.raw_calls.append((path, params))
        if self.raise_on_raw:
            raise RuntimeError("模拟 Modrinth API 网络异常")
        return self.raw_responses.get(path, (404, None))

    async def get_project(self, identifier: str) -> Optional[ProjectInfo]:
        return self.projects.get(identifier)

    async def get_version(
        self,
        project_id: str,
        mc_version: str,
        loader: str,
        specific_version: Optional[str] = None,
    ) -> tuple:
        return self.versions.get((project_id, mc_version, loader), (None, None))

    async def search(
        self,
        query: str,
        *,
        project_type: Optional[str] = None,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 5,
    ) -> list:
        return []

    async def get_loader_version(self, loader: str, mc_version: str) -> Optional[str]:
        return None

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture
def app(fake_catalog: FakeCatalog):
    """构造 FastAPI 应用，catalog 替换为离线桩（job_manager 保持真实实例）"""
    from modfetch.server.app import create_app

    application = create_app()
    application.state.catalog = fake_catalog
    return application


@pytest.fixture
def client(app):
    """TestClient：进入上下文触发 startup/shutdown 生命周期"""
    with TestClient(app) as test_client:
        yield test_client