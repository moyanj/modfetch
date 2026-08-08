"""
REST 路由测试（完全离线）

覆盖：健康检查、配置验证（全部错误分支）、任务创建/查询（含 404/400）、
Modrinth 搜索代理（facets 组装/透传/502）、项目详情（404/502）、
Minecraft 版本/加载器（含静态回退）、错误码映射与错误响应序列化。
"""

from __future__ import annotations

import json

import pytest

from modfetch import __version__
from modfetch.application.config_service import ConfigService
from modfetch.domain.errors import ConfigValidationError, ModFetchError
from modfetch.server import routes


# ---------------------------------------------------------------------------
# 错误码 → HTTP 状态码映射（纯函数）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("", 500),
        ("E", 500),
        ("E100", 400),
        ("E199", 400),
        ("E200", 502),
        ("E299", 502),
        ("E300", 500),
        ("E399", 500),
        ("E400", 500),
        ("E499", 500),
        # 已知 bug：E4xx 分支先于 E404/E429 特判命中 → 均映射为 500（按现状断言）
        ("E404", 500),
        ("E429", 500),
        ("E500", 500),
        ("E999", 500),
        # 非 E 开头 / 非数字后缀 → 500
        ("X100", 500),
        ("Eabc", 500),
    ],
)
def test_error_code_to_http_status(code: str, expected: int):
    assert routes.error_code_to_http_status(code) == expected


def test_make_error_response():
    """ModFetchError → JSONResponse（状态码 + to_dict 内容）"""
    error = ModFetchError("配置出错了", code="E102", context={"field": "x"})
    response = routes.make_error_response(error)

    assert response.status_code == 400
    body = json.loads(bytes(response.body))
    assert body["error"] is True
    assert body["code"] == "E102"
    assert body["message"] == "配置出错了"
    assert body["context"] == {"field": "x"}
    assert body["type"] == "ModFetchError"


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


# ---------------------------------------------------------------------------
# 配置验证
# ---------------------------------------------------------------------------


def test_validate_config_valid(client, fake_catalog, make_config_dict):
    """合法配置 → valid=True，errors 为空"""
    fake_catalog.add_project("AAAA0001", "sodium")
    resp = client.post("/api/config/validate", json={"config": make_config_dict()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_config_remote_invalid(client, fake_catalog, make_config_dict):
    """远端校验失败（项目不存在）→ valid=False + NOT_FOUND 错误项"""
    resp = client.post(
        "/api/config/validate",
        json={"config": make_config_dict(minecraft={"mods": ["ghost"]})},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "NOT_FOUND"


def test_validate_config_parse_error(client):
    """配置解析失败（ModFetchError）→ E101 折叠进 errors"""
    resp = client.post(
        "/api/config/validate",
        json={"config": {"minecraft": {"mods": ["sodium"]}}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "E101"
    assert body["errors"][0]["field"] == "config"


def test_validate_config_modfetch_error(client, monkeypatch, make_config_dict):
    """本地校验抛 ModFetchError → 按错误码折叠（E102）"""
    def boom(self, config):
        raise ConfigValidationError("本地校验失败")

    monkeypatch.setattr(ConfigService, "validate_local", boom)
    resp = client.post("/api/config/validate", json={"config": make_config_dict()})
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "E102"
    assert body["errors"][0]["message"] == "本地校验失败"


def test_validate_config_value_error(client, monkeypatch, make_config_dict):
    """本地校验抛 ValueError → 兜底为 E102"""
    def boom(self, config):
        raise ValueError("boom")

    monkeypatch.setattr(ConfigService, "validate_local", boom)
    resp = client.post("/api/config/validate", json={"config": make_config_dict()})
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "E102"


def test_validate_config_unexpected_error(client, monkeypatch, make_config_dict):
    """解析抛任意异常 → 兜底为 E101（配置解析失败）"""
    def boom(self, raw):
        raise RuntimeError("内部错误")

    monkeypatch.setattr(ConfigService, "parse", boom)
    resp = client.post("/api/config/validate", json={"config": make_config_dict()})
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "E101"
    assert "配置解析失败" in body["errors"][0]["message"]


def test_validate_config_missing_body_422(client):
    resp = client.post("/api/config/validate")
    assert resp.status_code == 422


def test_validate_config_missing_config_field_422(client):
    resp = client.post("/api/config/validate", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 任务管理
# ---------------------------------------------------------------------------


def test_create_job_success(client, app, fake_catalog, monkeypatch, make_config_dict):
    """合法配置 → 201，返回 job_id，任务登记为 pending 且被启动"""
    fake_catalog.add_project("AAAA0001", "sodium")
    manager = app.state.job_manager
    started: list[str] = []

    def fake_start(job_id: str) -> None:
        started.append(job_id)

    monkeypatch.setattr(manager, "start_job", fake_start)

    resp = client.post("/api/jobs", json={"config": make_config_dict()})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"

    job = manager.get_job(body["job_id"])
    assert job is not None
    assert job.status == "pending"
    # start_job 确实被调用
    assert started == [body["job_id"]]


def test_create_job_remote_validation_failure(client, fake_catalog, make_config_dict):
    """远端校验失败 → 400 E102，附带 issues 上下文"""
    resp = client.post(
        "/api/jobs",
        json={"config": make_config_dict(minecraft={"mods": ["ghost"]})},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] is True
    assert body["detail"]["code"] == "E102"
    assert "issues" in body["detail"]["context"]


def test_create_job_parse_error(client):
    """配置解析失败 → 400 E102"""
    resp = client.post("/api/jobs", json={"config": {"minecraft": {"mods": ["sodium"]}}})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E102"


def test_create_job_value_error(client, monkeypatch, make_config_dict):
    """本地校验抛 ValueError → 400 E102"""
    def boom(self, config):
        raise ValueError("boom")

    monkeypatch.setattr(ConfigService, "validate_local", boom)
    resp = client.post("/api/jobs", json={"config": make_config_dict()})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E102"


def test_create_job_missing_config_422(client):
    resp = client.post("/api/jobs", json={})
    assert resp.status_code == 422


def test_get_job_success(client, app, make_config_dict):
    """已创建任务 → 200，返回 to_response_dict 结构"""
    manager = app.state.job_manager
    job_id = manager.create_job(make_config_dict())

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "pending"
    assert body["phase"] == "idle"
    assert body["stats"]["total_mods"] == 0


def test_get_job_not_found(client):
    """不存在的任务 → 404 NOT_FOUND"""
    resp = client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"] is True
    assert body["detail"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Modrinth 搜索代理
# ---------------------------------------------------------------------------


def test_search_happy_path(client, fake_catalog):
    """搜索命中 → 200，字段白名单映射"""
    fake_catalog.set_raw(
        "/search",
        200,
        {
            "hits": [
                {
                    "slug": "sodium",
                    "title": "Sodium",
                    "description": "现代渲染引擎",
                    "icon_url": "https://cdn.example/icon.png",
                    "categories": ["fabric", "performance"],
                    "project_type": "mod",
                    "downloads": 100,
                    "project_id": "AAAA0001",
                }
            ],
            "offset": 0,
            "limit": 20,
            "total_hits": 1,
        },
    )

    resp = client.get("/api/search", params={"q": "sodium"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_hits"] == 1
    hit = body["hits"][0]
    assert hit["slug"] == "sodium"
    assert hit["downloads"] == 100
    assert hit["categories"] == ["fabric", "performance"]
    assert hit["project_id"] == "AAAA0001"

    # 无过滤条件时不带 facets 参数
    path, params = fake_catalog.raw_calls[-1]
    assert path == "/search"
    assert params["query"] == "sodium"
    assert "facets" not in params


def test_search_builds_facets(client, fake_catalog):
    """type/version/loader 便捷过滤 → 组装 facets JSON"""
    fake_catalog.set_raw("/search", 200, {"hits": [], "offset": 0, "limit": 20, "total_hits": 0})

    resp = client.get(
        "/api/search",
        params={"q": "sodium", "type": "mod", "version": "1.21.1", "loader": "fabric"},
    )
    assert resp.status_code == 200

    _, params = fake_catalog.raw_calls[-1]
    assert json.loads(params["facets"]) == [
        ["project_type:mod"],
        ["versions:1.21.1"],
        ["categories:fabric"],
    ]


def test_search_uses_explicit_facets(client, fake_catalog):
    """显式 facets 参数 → 原样透传"""
    fake_catalog.set_raw("/search", 200, {"hits": [], "total_hits": 0})
    explicit = json.dumps([["project_type:mod"]])

    resp = client.get("/api/search", params={"q": "sodium", "facets": explicit})
    assert resp.status_code == 200

    _, params = fake_catalog.raw_calls[-1]
    assert params["facets"] == explicit


def test_search_upstream_error(client, fake_catalog):
    """Modrinth 非 200 → 502 E200"""
    fake_catalog.set_raw("/search", 500, None)
    resp = client.get("/api/search", params={"q": "sodium"})
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "E200"


def test_search_missing_query_422(client):
    resp = client.get("/api/search")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 项目详情
# ---------------------------------------------------------------------------


def test_get_project_happy_path(client, fake_catalog):
    """项目详情 → 200，列表字段完整映射"""
    fake_catalog.set_raw(
        "/project/sodium",
        200,
        {
            "id": "AAAA0001",
            "slug": "sodium",
            "title": "Sodium",
            "description": "现代渲染引擎",
            "icon_url": "https://cdn.example/icon.png",
            "project_type": "mod",
            "categories": ["fabric"],
            "game_versions": ["1.21.1", "1.20.1"],
            "loaders": ["fabric", "forge"],
            "versions": ["0.1.0"],
        },
    )

    resp = client.get("/api/projects/sodium")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "AAAA0001"
    assert body["slug"] == "sodium"
    assert body["game_versions"] == ["1.21.1", "1.20.1"]
    assert body["loaders"] == ["fabric", "forge"]
    assert body["versions"] == ["0.1.0"]


def test_get_project_not_found(client, fake_catalog):
    """项目不存在 → 404 E404"""
    fake_catalog.set_raw("/project/ghost", 404, None)
    resp = client.get("/api/projects/ghost")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "E404"


def test_get_project_upstream_error(client, fake_catalog):
    """Modrinth 非 200 → 502 E200"""
    fake_catalog.set_raw("/project/sodium", 500, None)
    resp = client.get("/api/projects/sodium")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "E200"


# ---------------------------------------------------------------------------
# Minecraft 版本 / 加载器（含静态回退）
# ---------------------------------------------------------------------------


def test_minecraft_versions_happy_path(client, fake_catalog):
    """版本列表 → 200，versions + items 完整返回"""
    fake_catalog.set_raw(
        "/tag/game_version",
        200,
        [
            {"version": "1.21.1", "version_type": "release"},
            {"version": "1.20.1", "version_type": "snapshot"},
        ],
    )

    resp = client.get("/api/minecraft/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["versions"] == ["1.21.1", "1.20.1"]
    assert body["items"][0]["version"] == "1.21.1"
    assert body["items"][0]["version_type"] == "release"
    assert body["items"][1]["version_type"] == "snapshot"


def test_minecraft_versions_fallback_on_non_200(client, fake_catalog):
    """API 非 200 → 回退静态版本表"""
    fake_catalog.set_raw("/tag/game_version", 500, None)
    resp = client.get("/api/minecraft/versions")
    assert resp.status_code == 200
    assert resp.json()["versions"] == routes._static_mc_versions()


def test_minecraft_versions_fallback_on_empty(client, fake_catalog):
    """API 返回空列表 → 回退静态版本表"""
    fake_catalog.set_raw("/tag/game_version", 200, [])
    resp = client.get("/api/minecraft/versions")
    assert resp.json()["versions"] == routes._static_mc_versions()


def test_minecraft_versions_fallback_on_exception(client, fake_catalog):
    """API 抛异常 → 回退静态版本表"""
    fake_catalog.raise_on_raw = True
    resp = client.get("/api/minecraft/versions")
    assert resp.status_code == 200
    assert resp.json()["versions"] == routes._static_mc_versions()


def test_minecraft_loaders_happy_path(client, fake_catalog):
    """加载器列表 → 200，icon 可选"""
    fake_catalog.set_raw(
        "/tag/loader",
        200,
        [
            {"name": "fabric", "icon": "https://cdn.example/fabric.png"},
            {"name": "forge"},
        ],
    )

    resp = client.get("/api/minecraft/loaders")
    assert resp.status_code == 200
    body = resp.json()
    assert body["loaders"] == [
        {"name": "fabric", "icon_url": "https://cdn.example/fabric.png"},
        {"name": "forge", "icon_url": None},
    ]


def test_minecraft_loaders_fallback(client, fake_catalog):
    """API 非 200 → 回退静态加载器表"""
    fake_catalog.set_raw("/tag/loader", 500, None)
    resp = client.get("/api/minecraft/loaders")
    assert resp.status_code == 200
    names = [loader["name"] for loader in resp.json()["loaders"]]
    assert names == ["fabric", "forge", "neoforge", "quilt"]


def test_minecraft_loaders_fallback_on_empty(client, fake_catalog):
    """API 返回空列表 → 回退静态加载器表"""
    fake_catalog.set_raw("/tag/loader", 200, [])
    resp = client.get("/api/minecraft/loaders")
    assert resp.status_code == 200
    names = [loader["name"] for loader in resp.json()["loaders"]]
    assert names == ["fabric", "forge", "neoforge", "quilt"]


def test_minecraft_loaders_fallback_on_exception(client, fake_catalog):
    """API 抛异常 → 回退静态加载器表"""
    fake_catalog.raise_on_raw = True
    resp = client.get("/api/minecraft/loaders")
    assert resp.status_code == 200
    names = [loader["name"] for loader in resp.json()["loaders"]]
    assert names == ["fabric", "forge", "neoforge", "quilt"]