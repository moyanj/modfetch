"""
Pydantic 请求/响应模型（仅保留路由实际使用的 DTO）

任务状态响应由 JobState.to_response_dict() 直接产出（见
adapters/jobs/state.py），不经过 Pydantic 模型。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class ValidateConfigRequest(BaseModel):
    """配置验证请求"""

    config: dict[str, object]


class CreateJobRequest(BaseModel):
    """创建任务请求"""

    config: dict[str, object]


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    version: str


class ValidationErrorItem(BaseModel):
    """配置验证错误项"""

    field: str
    code: str
    message: str
    context: Optional[dict[str, object]] = None


class ValidateConfigResponse(BaseModel):
    """配置验证响应"""

    valid: bool
    errors: List[ValidationErrorItem] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    """创建任务响应"""

    job_id: str
    status: str


class SearchHit(BaseModel):
    """搜索结果项"""

    slug: str
    title: str
    description: str
    icon_url: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    project_type: str = ""
    downloads: int = 0
    project_id: str = ""


class SearchResponse(BaseModel):
    """搜索响应"""

    hits: List[SearchHit]
    offset: int = 0
    limit: int = 20
    total_hits: int = 0


class ProjectResponse(BaseModel):
    """项目信息响应"""

    id: str
    slug: str
    title: str
    description: str
    icon_url: Optional[str] = None
    project_type: str = ""
    categories: List[str] = Field(default_factory=list)
    game_versions: List[str] = Field(default_factory=list)
    loaders: List[str] = Field(default_factory=list)
    versions: List[str] = Field(default_factory=list)


class MinecraftVersionItem(BaseModel):
    """Minecraft 版本项"""

    version: str
    version_type: str = "release"


class MinecraftVersionsResponse(BaseModel):
    """Minecraft 版本列表响应"""

    versions: List[str]
    items: List[MinecraftVersionItem] = Field(default_factory=list)


class LoaderInfo(BaseModel):
    """加载器信息"""

    name: str
    icon_url: Optional[str] = None


class MinecraftLoadersResponse(BaseModel):
    """加载器列表响应"""

    loaders: List[LoaderInfo]
