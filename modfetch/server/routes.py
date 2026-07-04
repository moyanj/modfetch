"""
REST API 路由

提供健康检查、配置验证、任务管理、Modrinth 搜索代理等端点。
"""

from __future__ import annotations

import os
from typing import Optional

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from modfetch.exceptions import ModFetchError
from modfetch.models import ModFetchConfig
from modfetch.server import schemas
from modfetch.server.jobs import JobManager

router = APIRouter(prefix="/api")

# Modrinth API 基础 URL
MODRINTH_BASE = "https://api.modrinth.com/v2"

# 项目版本 (从 pyproject.toml 读取，回退到硬编码)
APP_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# 错误码 → HTTP 状态码映射
# ---------------------------------------------------------------------------


def error_code_to_http_status(code: str) -> int:
    """将 ModFetch 错误代码映射到 HTTP 状态码"""
    if not code or not code.startswith("E"):
        return 500

    num_str = code[1:]
    try:
        num = int(num_str)
    except ValueError:
        return 500

    # E1xx → 400 (配置错误)
    if 100 <= num < 200:
        return 400
    # E2xx → 502 (API 错误)
    if 200 <= num < 300:
        return 502
    # E3xx → 500 (下载错误)
    if 300 <= num < 400:
        return 500
    # E4xx → 500 (打包错误)
    if 400 <= num < 500:
        return 500
    # E404 → 404
    if num == 404:
        return 404
    # E429 → 429
    if num == 429:
        return 429
    # E500 → 500
    if num == 500:
        return 500
    return 500


def make_error_response(error: ModFetchError) -> JSONResponse:
    """从 ModFetchError 创建 JSON 错误响应"""
    return JSONResponse(
        status_code=error_code_to_http_status(error.code),
        content=error.to_dict(),
    )


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


@router.get("/health", response_model=schemas.HealthResponse)
async def health() -> schemas.HealthResponse:
    """健康检查"""
    return schemas.HealthResponse(status="ok", version=APP_VERSION)


# ---------------------------------------------------------------------------
# 配置验证
# ---------------------------------------------------------------------------


@router.post("/config/validate", response_model=schemas.ValidateConfigResponse)
async def validate_config(
    request: schemas.ValidateConfigRequest,
) -> schemas.ValidateConfigResponse:
    """验证配置文件"""
    errors: list[schemas.ValidationErrorItem] = []

    try:
        config = ModFetchConfig.from_dict(request.config)
        config.validate()
    except ValueError as e:
        errors.append(
            schemas.ValidationErrorItem(
                field="config",
                code="E102",
                message=str(e),
            )
        )
    except ModFetchError as e:
        errors.append(
            schemas.ValidationErrorItem(
                field="config",
                code=e.code,
                message=e.message,
            )
        )
    except Exception as e:
        errors.append(
            schemas.ValidationErrorItem(
                field="config",
                code="E101",
                message=f"配置解析失败: {e}",
            )
        )

    if errors:
        return schemas.ValidateConfigResponse(valid=False, errors=errors)
    return schemas.ValidateConfigResponse(valid=True, errors=[])


# ---------------------------------------------------------------------------
# 任务管理
# ---------------------------------------------------------------------------


@router.post("/jobs", response_model=schemas.CreateJobResponse, status_code=201)
async def create_job(
    request: schemas.CreateJobRequest,
    http_request: Request,
) -> schemas.CreateJobResponse:
    """创建并启动新任务"""
    job_manager: JobManager = http_request.app.state.job_manager

    # 先验证配置
    try:
        ModFetchConfig.from_dict(request.config)
    except (ValueError, ModFetchError) as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": True,
                "code": "E102",
                "message": str(e),
            },
        )

    job_id = job_manager.create_job(request.config)
    job_manager.start_job(job_id)

    return schemas.CreateJobResponse(job_id=job_id, status="pending")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, http_request: Request) -> JSONResponse:
    """获取任务状态"""
    job_manager: JobManager = http_request.app.state.job_manager
    job = job_manager.get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": True,
                "code": "NOT_FOUND",
                "message": f"任务 {job_id} 不存在",
            },
        )

    return JSONResponse(status_code=200, content=job.to_response_dict())


# ---------------------------------------------------------------------------
# Modrinth 搜索代理
# ---------------------------------------------------------------------------


@router.get("/search", response_model=schemas.SearchResponse)
async def search(
    q: str,
    limit: int = 20,
    offset: int = 0,
    facets: Optional[str] = None,
) -> schemas.SearchResponse:
    """代理 Modrinth 搜索 API"""
    params: dict[str, str] = {
        "query": q,
        "limit": str(limit),
        "offset": str(offset),
    }
    if facets:
        params["facets"] = facets

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MODRINTH_BASE}/search", params=params
        ) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": True,
                        "code": "E200",
                        "message": f"Modrinth API 返回 {response.status}",
                    },
                )
            data = await response.json()

    hits: list[schemas.SearchHit] = []
    for hit in data.get("hits", []):
        hits.append(
            schemas.SearchHit(
                slug=str(hit.get("slug", "")),
                title=str(hit.get("title", "")),
                description=str(hit.get("description", "")),
                icon_url=hit.get("icon_url"),
                categories=hit.get("categories", []) if isinstance(
                    hit.get("categories"), list
                ) else [],
                project_type=str(hit.get("project_type", "")),
                downloads=int(hit.get("downloads", 0)),
                project_id=str(hit.get("project_id", "")),
            )
        )

    return schemas.SearchResponse(
        hits=hits,
        offset=int(data.get("offset", offset)),
        limit=int(data.get("limit", limit)),
        total_hits=int(data.get("total_hits", len(hits))),
    )


@router.get("/projects/{slug_or_id}", response_model=schemas.ProjectResponse)
async def get_project(slug_or_id: str) -> schemas.ProjectResponse:
    """代理 Modrinth 项目信息 API"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MODRINTH_BASE}/project/{slug_or_id}"
        ) as response:
            if response.status == 404:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": True,
                        "code": "E404",
                        "message": f"项目 {slug_or_id} 不存在",
                    },
                )
            if response.status != 200:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": True,
                        "code": "E200",
                        "message": f"Modrinth API 返回 {response.status}",
                    },
                )
            data = await response.json()

    return schemas.ProjectResponse(
        id=str(data.get("id", "")),
        slug=str(data.get("slug", "")),
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        icon_url=data.get("icon_url"),
        project_type=str(data.get("project_type", "")),
        categories=data.get("categories", []) if isinstance(
            data.get("categories"), list
        ) else [],
        game_versions=data.get("game_versions", []) if isinstance(
            data.get("game_versions"), list
        ) else [],
        loaders=[
            str(l) for l in data.get("loaders", [])
            if isinstance(data.get("loaders"), list)
        ],
        versions=data.get("versions", []) if isinstance(
            data.get("versions"), list
        ) else [],
    )


# ---------------------------------------------------------------------------
# Minecraft 版本和加载器
# ---------------------------------------------------------------------------


@router.get("/minecraft/versions", response_model=schemas.MinecraftVersionsResponse)
async def minecraft_versions() -> schemas.MinecraftVersionsResponse:
    """获取 Minecraft 版本列表 (代理 Modrinth tag API)"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MODRINTH_BASE}/tag/game_version"
            ) as response:
                if response.status != 200:
                    return schemas.MinecraftVersionsResponse(
                        versions=_static_mc_versions(),
                        items=_static_mc_version_items(),
                    )
                data = await response.json()

        versions: list[str] = []
        items: list[schemas.MinecraftVersionItem] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    version = item.get("version")
                    if isinstance(version, str):
                        versions.append(version)
                        items.append(
                            schemas.MinecraftVersionItem(
                                version=version,
                                version_type=str(item.get("version_type", "release")),
                            )
                        )

        if not versions:
            return schemas.MinecraftVersionsResponse(
                versions=_static_mc_versions(),
                items=_static_mc_version_items(),
            )

        return schemas.MinecraftVersionsResponse(versions=versions, items=items)

    except Exception as e:
        logger.warning(f"获取 Minecraft 版本失败: {e}")
        return schemas.MinecraftVersionsResponse(
            versions=_static_mc_versions(),
            items=_static_mc_version_items(),
        )


@router.get("/minecraft/loaders", response_model=schemas.MinecraftLoadersResponse)
async def minecraft_loaders() -> schemas.MinecraftLoadersResponse:
    """获取模组加载器列表 (代理 Modrinth tag API)"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MODRINTH_BASE}/tag/loader"
            ) as response:
                if response.status != 200:
                    return schemas.MinecraftLoadersResponse(
                        loaders=_static_loaders()
                    )
                data = await response.json()

        loaders: list[schemas.LoaderInfo] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str):
                        icon = item.get("icon")
                        loaders.append(
                            schemas.LoaderInfo(
                                name=name,
                                icon_url=str(icon) if isinstance(icon, str) else None,
                            )
                        )

        if not loaders:
            return schemas.MinecraftLoadersResponse(loaders=_static_loaders())

        return schemas.MinecraftLoadersResponse(loaders=loaders)

    except Exception as e:
        logger.warning(f"获取加载器列表失败: {e}")
        return schemas.MinecraftLoadersResponse(loaders=_static_loaders())


# ---------------------------------------------------------------------------
# 静态回退数据
# ---------------------------------------------------------------------------


def _static_mc_versions() -> list[str]:
    """静态 Minecraft 版本列表 (API 不可用时的回退)"""
    return [
        "1.21.4",
        "1.21.1",
        "1.20.6",
        "1.20.4",
        "1.20.1",
        "1.19.4",
        "1.19.2",
        "1.18.2",
        "1.17.1",
        "1.16.5",
        "1.12.2",
    ]


def _static_mc_version_items() -> list[schemas.MinecraftVersionItem]:
    """静态 Minecraft 版本元数据 (API 不可用时的回退)"""
    return [
        schemas.MinecraftVersionItem(version=version, version_type="release")
        for version in _static_mc_versions()
    ]


def _static_loaders() -> list[schemas.LoaderInfo]:
    """静态加载器列表 (API 不可用时的回退)"""
    return [
        schemas.LoaderInfo(name="fabric"),
        schemas.LoaderInfo(name="forge"),
        schemas.LoaderInfo(name="neoforge"),
        schemas.LoaderInfo(name="quilt"),
    ]
