"""
Pydantic schema 序列化测试

覆盖 server/schemas.py 全部请求/响应模型：构造、默认值、
model_dump 序列化（与 FastAPI response_model 使用的字段一致）。
"""

from __future__ import annotations

from modfetch.server import schemas


def test_validate_config_request():
    model = schemas.ValidateConfigRequest(config={"minecraft": {}})
    assert model.config == {"minecraft": {}}


def test_create_job_request():
    model = schemas.CreateJobRequest(config={"minecraft": {}})
    assert model.model_dump() == {"config": {"minecraft": {}}}


def test_health_response():
    model = schemas.HealthResponse(status="ok", version="1.0.1")
    assert model.model_dump() == {"status": "ok", "version": "1.0.1"}


def test_validation_error_item_context_optional():
    item = schemas.ValidationErrorItem(field="config", code="E101", message="x")
    assert item.context is None
    assert item.model_dump()["context"] is None

    item2 = schemas.ValidationErrorItem(
        field="config", code="E101", message="x", context={"k": 1}
    )
    assert item2.context == {"k": 1}


def test_validate_config_response_errors_default():
    resp = schemas.ValidateConfigResponse(valid=True)
    assert resp.errors == []
    assert resp.model_dump() == {"valid": True, "errors": []}


def test_create_job_response():
    resp = schemas.CreateJobResponse(job_id="abc", status="pending")
    assert resp.model_dump() == {"job_id": "abc", "status": "pending"}


def test_search_hit_defaults():
    hit = schemas.SearchHit(slug="sodium", title="Sodium", description="d")
    data = hit.model_dump()
    assert data["icon_url"] is None
    assert data["categories"] == []
    assert data["project_type"] == ""
    assert data["downloads"] == 0
    assert data["project_id"] == ""


def test_search_response_defaults():
    resp = schemas.SearchResponse(hits=[])
    assert resp.offset == 0
    assert resp.limit == 20
    assert resp.total_hits == 0


def test_project_response_defaults():
    proj = schemas.ProjectResponse(id="1", slug="s", title="S", description="d")
    data = proj.model_dump()
    assert data["icon_url"] is None
    assert data["categories"] == []
    assert data["game_versions"] == []
    assert data["loaders"] == []
    assert data["versions"] == []


def test_minecraft_version_item_default_type():
    item = schemas.MinecraftVersionItem(version="1.21.1")
    assert item.version_type == "release"


def test_minecraft_versions_response():
    resp = schemas.MinecraftVersionsResponse(
        versions=["1.21.1"],
        items=[schemas.MinecraftVersionItem(version="1.20.1", version_type="snapshot")],
    )
    data = resp.model_dump()
    assert data["versions"] == ["1.21.1"]
    assert data["items"] == [
        {"version": "1.20.1", "version_type": "snapshot"}
    ]


def test_loader_info_icon_optional():
    loader = schemas.LoaderInfo(name="fabric")
    assert loader.icon_url is None
    loader2 = schemas.LoaderInfo(name="forge", icon_url="https://x/icon.png")
    assert loader2.icon_url == "https://x/icon.png"


def test_minecraft_loaders_response():
    resp = schemas.MinecraftLoadersResponse(loaders=[schemas.LoaderInfo(name="fabric")])
    assert resp.model_dump() == {"loaders": [{"name": "fabric", "icon_url": None}]}