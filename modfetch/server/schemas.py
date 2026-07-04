"""
Pydantic 请求/响应模型

镜像 modfetch/models 中的 dataclass 模型，供 FastAPI 接口层使用。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union, List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举镜像
# ---------------------------------------------------------------------------


class ModLoaderEnum(str, Enum):
    """模组加载器"""

    FORGE = "forge"
    NEOFORGE = "neoforge"
    FABRIC = "fabric"
    QUILT = "quilt"


class OutputFormatEnum(str, Enum):
    """输出格式"""

    ZIP = "zip"
    MRPACK = "mrpack"


class MrpackModeEnum(str, Enum):
    """Mrpack 模式"""

    DOWNLOAD = "download"
    REFERENCE = "reference"


# ---------------------------------------------------------------------------
# 配置模型镜像
# ---------------------------------------------------------------------------


class ModEntrySchema(BaseModel):
    """模组条目"""

    id: Optional[str] = None
    slug: Optional[str] = None
    only_version: Optional[Union[str, List[str]]] = None
    feature: Optional[Union[str, List[str]]] = None


class ExtraUrlSchema(BaseModel):
    """额外下载链接"""

    url: str
    filename: Optional[str] = None
    type: str = "file"
    sha1: Optional[str] = None
    only_version: Optional[Union[str, List[str]]] = None
    feature: Optional[Union[str, List[str]]] = None


class MinecraftConfigSchema(BaseModel):
    """Minecraft 配置"""

    version: List[str] = Field(default_factory=list)
    mod_loader: Union[ModLoaderEnum, List[ModLoaderEnum]] = ModLoaderEnum.FABRIC
    mods: List[Union[str, ModEntrySchema]] = Field(default_factory=list)
    resourcepacks: List[Union[str, ModEntrySchema]] = Field(default_factory=list)
    shaderpacks: List[Union[str, ModEntrySchema]] = Field(default_factory=list)
    extra_urls: List[ExtraUrlSchema] = Field(default_factory=list)


class OutputConfigSchema(BaseModel):
    """输出配置"""

    download_dir: str = "downloads"
    format: List[OutputFormatEnum] = Field(default_factory=lambda: [OutputFormatEnum.ZIP])
    mrpack_modes: List[MrpackModeEnum] = Field(
        default_factory=lambda: [MrpackModeEnum.DOWNLOAD]
    )


class MetadataConfigSchema(BaseModel):
    """元数据配置"""

    name: str = "ModFetch Pack"
    version: str = "1.0.0"
    description: str = ""


class PluginConfigSchema(BaseModel):
    """插件配置"""

    enabled: List[str] = Field(default_factory=list)
    configs: dict[str, dict[str, object]] = Field(default_factory=dict)


class ModFetchConfigSchema(BaseModel):
    """ModFetch 主配置"""

    minecraft: MinecraftConfigSchema
    output: Optional[OutputConfigSchema] = None
    metadata: Optional[MetadataConfigSchema] = None
    max_concurrent: int = 5
    max_retries: int = 3
    retry_delay: float = 1.0
    features: List[str] = Field(default_factory=list)
    plugins: Optional[PluginConfigSchema] = None


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


class JobStatsResponse(BaseModel):
    """任务统计"""

    total_mods: int = 0
    resolved: int = 0
    downloaded: int = 0
    failed: int = 0
    bytes_downloaded: int = 0


class JobResultItem(BaseModel):
    """任务结果项"""

    filename: str
    path: str
    size: int
    format: str
    mc_version: str
    loader: str


class JobErrorItem(BaseModel):
    """任务错误项"""

    code: str
    message: str
    context: Optional[dict[str, object]] = None


class JobStateResponse(BaseModel):
    """任务状态响应"""

    id: str
    status: str
    phase: str
    stats: JobStatsResponse
    results: Optional[List[JobResultItem]] = None
    errors: Optional[List[JobErrorItem]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


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


class MinecraftVersionsResponse(BaseModel):
    """Minecraft 版本列表响应"""

    versions: List[str]
    items: List[MinecraftVersionItem] = Field(default_factory=list)


class MinecraftVersionItem(BaseModel):
    """Minecraft 版本项"""

    version: str
    version_type: str = "release"


class LoaderInfo(BaseModel):
    """加载器信息"""

    name: str
    icon_url: Optional[str] = None


class MinecraftLoadersResponse(BaseModel):
    """加载器列表响应"""

    loaders: List[LoaderInfo]


class ErrorResponse(BaseModel):
    """通用错误响应"""

    error: bool = True
    code: str
    message: str
    context: Optional[dict[str, object]] = None
    type: Optional[str] = None
