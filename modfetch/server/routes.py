"""
REST API 路由

提供健康检查、配置验证、任务管理、Modrinth 搜索代理等端点。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from modfetch.adapters.modrinth import build_modrinth_facets
from modfetch.application.config_service import ConfigService
from modfetch.application.validation import validation_issue_to_dict
from modfetch.domain.errors import ModFetchError
from modfetch.ports.catalog import CatalogPort
from modfetch.server import schemas
from modfetch.adapters.jobs import JobManager

router = APIRouter(prefix="/api")

# 项目版本
APP_VERSION = "0.2.0"


def _catalog(request: Request) -> CatalogPort:
    """从 app.state 获取共享 catalog（由 app 工厂注入）"""
    return request.app.state.catalog


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
    """健康检查

    用途：探活端点，供负载均衡/前端判断服务可用性。
    请求：无参数。
    响应：200，{status: "ok", version: <APP_VERSION>}。
    错误码：无（恒 200）。
    """
    return schemas.HealthResponse(status="ok", version=APP_VERSION)


# ---------------------------------------------------------------------------
# 配置验证
# ---------------------------------------------------------------------------


@router.post("/config/validate", response_model=schemas.ValidateConfigResponse)
async def validate_config(
    request: schemas.ValidateConfigRequest,
    http_request: Request,
) -> schemas.ValidateConfigResponse:
    """验证配置文件

    用途：对提交的配置做本地 + 远端（Modrinth）双重校验，供前端在创建任务前预检。
    请求：{config: <原始配置字典>}。
    响应：200，{valid: bool, errors: [{field, code, message, context?}]}；
          valid=false 时 errors 含全部校验问题。
    错误码：不抛 HTTP 错误，校验失败统一折叠进 errors（E101/E102 等）。
    """
    errors: list[schemas.ValidationErrorItem] = []
    config_service = ConfigService()

    try:
        config = config_service.parse(request.config)
        config_service.validate_local(config)
        result = await config_service.validate_remote(
            config, _catalog(http_request)
        )
        if not result.is_valid:
            errors.extend(
                schemas.ValidationErrorItem(**validation_issue_to_dict(issue))
                for issue in result.issues
            )
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
                context=e.context,
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
    """创建并启动新任务

    用途：校验配置后创建作业并异步启动构建，返回作业 ID 供轮询/订阅。
    请求：{config: <原始配置字典>}。
    响应：201，{job_id: str, status: "pending"}。
    错误码：
        - 400：配置本地/远端校验失败（E102）
        - 其余 ModFetch 错误经 error_code_to_http_status 映射
    """
    job_manager: JobManager = http_request.app.state.job_manager

    # 先验证配置（统一配置边界）
    config_service = ConfigService()
    try:
        config = config_service.parse(request.config)
        config_service.validate_local(config)
        result = await config_service.validate_remote(
            config, _catalog(http_request)
        )
        if not result.is_valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": True,
                    "code": "E102",
                    "message": "远端校验失败",
                    "context": {
                        "issues": [
                            validation_issue_to_dict(issue)
                            for issue in result.issues
                        ]
                    },
                },
            )
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
    """获取任务状态

    用途：按 job_id 查询作业当前状态（status/phase/stats/results/errors），
          前端轮询用；实时推送请走 WebSocket /jobs/{job_id}/stream。
    请求：路径参数 job_id。
    响应：200，作业状态字典（JobState.to_response_dict() 结构）。
    错误码：
        - 404：任务不存在（NOT_FOUND）
    """
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
    http_request: Request,
    limit: int = 20,
    offset: int = 0,
    facets: Optional[str] = None,
    type: Optional[str] = None,
    loader: Optional[str] = None,
    version: Optional[str] = None,
) -> schemas.SearchResponse:
    """代理 Modrinth 搜索 API

    用途：将前端搜索请求转发到 Modrinth /search，并做字段白名单映射。
    请求（查询参数）：q 必填；limit/offset 分页；facets 原始过滤串；
          type/loader/version 便捷过滤（经 build_modrinth_facets 组装）。
    响应：200，{hits: [SearchHit...], offset, limit, total_hits}。
    错误码：
        - 502：Modrinth API 非 200（E200）
    """
    params: dict[str, str] = {
        "query": q,
        "limit": str(limit),
        "offset": str(offset),
    }
    merged_facets = facets or build_modrinth_facets(
        project_type=type,
        mc_version=version,
        mod_loader=loader,
    )
    if merged_facets:
        params["facets"] = merged_facets

    catalog = _catalog(http_request)
    status, data = await catalog.raw_get("/search", params=params)
    if status != 200 or data is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": True,
                "code": "E200",
                "message": f"Modrinth API 返回 {status}",
            },
        )

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
async def get_project(
    slug_or_id: str, http_request: Request
) -> schemas.ProjectResponse:
    """代理 Modrinth 项目信息 API

    用途：按 slug 或 ID 获取项目详情（含可用版本/加载器），供前端展示。
    请求：路径参数 slug_or_id（slug 或项目 ID）。
    响应：200，ProjectResponse（id/slug/title/description/categories 等）。
    错误码：
        - 404：项目不存在（E404）
        - 502：Modrinth API 非 200（E200）
    """
    catalog = _catalog(http_request)
    status, data = await catalog.raw_get(f"/project/{slug_or_id}")
    if status == 404:
        raise HTTPException(
            status_code=404,
            detail={
                "error": True,
                "code": "E404",
                "message": f"项目 {slug_or_id} 不存在",
            },
        )
    if status != 200 or data is None:
        raise HTTPException(
            status_code=502,
            detail={
                "error": True,
                "code": "E200",
                "message": f"Modrinth API 返回 {status}",
            },
        )

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
async def minecraft_versions(
    http_request: Request,
) -> schemas.MinecraftVersionsResponse:
    """获取 Minecraft 版本列表 (代理 Modrinth tag API)

    用途：下拉框数据源；Modrinth tag API 不可用时回退到静态版本表。
    请求：无参数。
    响应：200，MinecraftVersionsResponse（versions + 带 version_type 的 items）。
    错误码：无；API 异常降级为静态数据并告警日志。
    """
    try:
        status, data = await _catalog(http_request).raw_get("/tag/game_version")
        if status != 200:
            return schemas.MinecraftVersionsResponse(
                versions=_static_mc_versions(),
                items=_static_mc_version_items(),
            )

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
async def minecraft_loaders(
    http_request: Request,
) -> schemas.MinecraftLoadersResponse:
    """获取模组加载器列表 (代理 Modrinth tag API)

    用途：下拉框数据源；Modrinth tag API 不可用时回退到静态加载器表。
    请求：无参数。
    响应：200，MinecraftLoadersResponse（loaders: [{name, icon_url?}]）。
    错误码：无；API 异常降级为静态数据并告警日志。
    """
    try:
        status, data = await _catalog(http_request).raw_get("/tag/loader")
        if status != 200:
            return schemas.MinecraftLoadersResponse(loaders=_static_loaders())

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
