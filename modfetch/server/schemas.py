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
    """配置验证请求（POST /api/config/validate）"""

    config: dict[str, object]  #: 原始配置字典（TOML/YAML/JSON 解析后的裸数据）


class CreateJobRequest(BaseModel):
    """创建任务请求（POST /api/jobs）"""

    config: dict[str, object]  #: 原始配置字典，创建前经本地+远端校验


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """健康检查响应（GET /api/health）"""

    status: str  #: 服务状态，恒为 "ok"
    version: str  #: 服务版本号


class ValidationErrorItem(BaseModel):
    """配置验证错误项"""

    field: str  #: 出错字段（顶层错误时为 "config"）
    code: str  #: 错误码（E101/E102 等）
    message: str  #: 错误消息（中文）
    context: Optional[dict[str, object]] = None  #: 附加上下文（如远端 issues）


class ValidateConfigResponse(BaseModel):
    """配置验证响应（POST /api/config/validate）"""

    valid: bool  #: 是否通过全部校验
    errors: List[ValidationErrorItem] = Field(default_factory=list)  #: 校验错误列表


class CreateJobResponse(BaseModel):
    """创建任务响应（POST /api/jobs）"""

    job_id: str  #: 新作业 ID（后续查询/订阅用）
    status: str  #: 初始状态，恒为 "pending"


class SearchHit(BaseModel):
    """搜索结果项（GET /api/search hits 元素）"""

    slug: str  #: 项目 slug
    title: str  #: 显示标题
    description: str  #: 简介
    icon_url: Optional[str] = None  #: 图标地址
    categories: List[str] = Field(default_factory=list)  #: 类别标签
    project_type: str = ""  #: 项目类型（mod/resourcepack 等）
    downloads: int = 0  #: 下载量
    project_id: str = ""  #: 项目 ID


class SearchResponse(BaseModel):
    """搜索响应（GET /api/search）"""

    hits: List[SearchHit]  #: 命中列表
    offset: int = 0  #: 本次结果偏移
    limit: int = 20  #: 本次结果上限
    total_hits: int = 0  #: 总命中数


class ProjectResponse(BaseModel):
    """项目信息响应（GET /api/projects/{slug_or_id}）"""

    id: str  #: 项目 ID
    slug: str  #: 项目 slug
    title: str  #: 显示标题
    description: str  #: 简介
    icon_url: Optional[str] = None  #: 图标地址
    project_type: str = ""  #: 项目类型
    categories: List[str] = Field(default_factory=list)  #: 类别标签
    game_versions: List[str] = Field(default_factory=list)  #: 支持的 MC 版本
    loaders: List[str] = Field(default_factory=list)  #: 支持的加载器
    versions: List[str] = Field(default_factory=list)  #: 版本号列表


class MinecraftVersionItem(BaseModel):
    """Minecraft 版本项（GET /api/minecraft/versions items 元素）"""

    version: str  #: 版本号
    version_type: str = "release"  #: 版本类型：release / snapshot / beta / alpha


class MinecraftVersionsResponse(BaseModel):
    """Minecraft 版本列表响应（GET /api/minecraft/versions）"""

    versions: List[str]  #: 版本号列表
    items: List[MinecraftVersionItem] = Field(default_factory=list)  #: 版本元数据


class LoaderInfo(BaseModel):
    """加载器信息（GET /api/minecraft/loaders loaders 元素）"""

    name: str  #: 加载器名（fabric/forge/neoforge/quilt）
    icon_url: Optional[str] = None  #: 图标地址


class MinecraftLoadersResponse(BaseModel):
    """加载器列表响应（GET /api/minecraft/loaders）"""

    loaders: List[LoaderInfo]  #: 加载器列表
