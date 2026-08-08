"""
create_app 应用工厂测试

覆盖：工厂返回独立实例、状态注入、路由注册、静态挂载分支、
startup/shutdown 生命周期钩子。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import Mount
from fastapi.testclient import TestClient

import modfetch.server.app as app_module
from modfetch import __version__


def _route_paths(app: FastAPI) -> set[str]:
    """收集全部路由路径

    FastAPI 0.139 将 include_router 的路由包装为 _IncludedRouter，
    需穿透 include_context.included_router 才能拿到真实路径。
    """
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
            continue
        ctx = getattr(route, "include_context", None)
        router = getattr(ctx, "included_router", None)
        if router is not None:
            for sub in router.routes:
                sub_path = getattr(sub, "path", None)
                if sub_path:
                    paths.add(sub_path)
    return paths


def test_create_app_returns_configured_app():
    """工厂返回独立 FastAPI 实例，注入 job_manager/catalog 并注册全部路由"""
    app = app_module.create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "ModFetch API"
    assert app.version == __version__
    # 状态注入（REST/WS 共享）
    assert app.state.job_manager is not None
    assert app.state.catalog is not None

    # 路由注册（REST + WebSocket）
    paths = _route_paths(app)
    assert "/api/health" in paths
    assert "/api/config/validate" in paths
    assert "/api/jobs" in paths
    assert "/api/jobs/{job_id}" in paths
    assert "/api/search" in paths
    assert "/api/projects/{slug_or_id}" in paths
    assert "/api/minecraft/versions" in paths
    assert "/api/minecraft/loaders" in paths
    assert "/api/jobs/{job_id}/stream" in paths


def test_create_app_skips_static_mount_when_dist_missing():
    """web/dist 不存在（当前路径计算指向 modfetch/web/dist）→ 跳过挂载"""
    app = app_module.create_app()
    assert not any(isinstance(route, Mount) for route in app.routes)


def test_create_app_mounts_static_when_dist_exists(monkeypatch):
    """web/dist 存在 → 挂载静态文件（用假 Path/StaticFiles 避免真实文件系统）"""

    class FakePath:
        def __init__(self, *parts):
            self.parts = parts

        def __truediv__(self, other):
            return FakePath(*self.parts, str(other))

        @property
        def parent(self):
            return FakePath(*self.parts[:-1]) if self.parts else FakePath()

        def is_dir(self):
            return True

    class FakeStaticFiles:
        def __init__(self, directory, html=False):
            self.directory = directory
            self.html = html

    monkeypatch.setattr(app_module, "Path", FakePath)
    monkeypatch.setattr(app_module, "StaticFiles", FakeStaticFiles)

    app = app_module.create_app()
    mounts = [route for route in app.routes if isinstance(route, Mount)]
    assert len(mounts) == 1
    # 本版本 starlette 将 "/" 归一化为空串，以 name/app 类型断言
    assert mounts[0].name == "web"
    assert isinstance(mounts[0].app, FakeStaticFiles)


def test_lifecycle_startup_shutdown(app, fake_catalog):
    """TestClient 上下文触发 startup/shutdown，shutdown 关闭 catalog"""
    with TestClient(app) as test_client:
        # startup 后服务可用
        assert test_client.get("/api/health").status_code == 200
    # shutdown 钩子已执行：catalog.close() 被调用
    assert fake_catalog.closed is True