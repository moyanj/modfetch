"""
构建计划领域模型

BuildPlan 是「解析阶段」的不可变产出物，将配置展开为
具体的构建目标、制品与输出规格，供执行阶段消费。
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple

from modfetch.domain.config_models import ModLoader


@dataclass(frozen=True)
class BuildTarget:
    """单个构建目标：一个 (Minecraft 版本, 加载器) 组合"""

    minecraft_version: str
    loader: ModLoader

    @property
    def dir_name(self) -> str:
        """下载目录名（沿用旧命名约定: {version}-{loader}）"""
        return f"{self.minecraft_version}-{self.loader.value}"


@dataclass(frozen=True)
class ArtifactCategory:
    """制品类别（决定目标子目录与 mrpack env 标记）"""

    value: str  # "mods" / "resourcepacks" / "shaderpacks" / "file"

    @classmethod
    def mods(cls) -> "ArtifactCategory":
        return cls("mods")

    @classmethod
    def resourcepacks(cls) -> "ArtifactCategory":
        return cls("resourcepacks")

    @classmethod
    def shaderpacks(cls) -> "ArtifactCategory":
        return cls("shaderpacks")

    @classmethod
    def file(cls) -> "ArtifactCategory":
        return cls("file")


@dataclass(frozen=True)
class ResolvedArtifact:
    """一个已解析的待下载制品"""

    project_id: str
    project_name: str
    category: ArtifactCategory
    filename: str
    url: str
    hashes: Dict[str, str]
    destination: str  # 相对于版本目录的路径
    target: BuildTarget
    environment: Dict[str, str] = field(
        default_factory=lambda: {"client": "required", "server": "required"}
    )

    def to_mrpack_entry(self) -> dict:
        """转换为 mrpack manifest files 条目（沿用旧格式契约）"""
        return {
            "path": (
                self.destination
                if self.category.value == "file"
                else f"{self.category.value}/{self.filename}"
            ),
            "hashes": self.hashes,
            "env": self.environment,
            "downloads": [self.url],
            "fileSize": 0,
        }


@dataclass(frozen=True)
class OutputSpec:
    """输出规格：为某个 target 生成何种格式的包"""

    format: str  # "mrpack" / "zip"
    target: BuildTarget
    output_name: str  # 最终文件名（不含扩展名）
    mrpack_mode: str = "download"  # 仅 mrpack 有效: "download" / "reference"


@dataclass(frozen=True)
class BuildPlan:
    """构建计划：目标集合 + 制品集合 + 输出规格集合"""

    targets: Tuple[BuildTarget, ...]
    artifacts: Tuple[ResolvedArtifact, ...]
    outputs: Tuple[OutputSpec, ...]

    def artifacts_for(self, target: BuildTarget) -> Tuple[ResolvedArtifact, ...]:
        return tuple(a for a in self.artifacts if a.target == target)

    def outputs_for(self, target: BuildTarget) -> Tuple[OutputSpec, ...]:
        return tuple(o for o in self.outputs if o.target == target)


@dataclass(frozen=True)
class OutputArtifact:
    """一个已生成的输出文件"""

    path: str
    format: str
    target: BuildTarget
    size: int


@dataclass(frozen=True)
class BuildError:
    """结构化构建错误"""

    code: str
    message: str
    target: BuildTarget
    phase: str  # "resolve" / "download" / "package"
    context: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildStats:
    """构建统计"""

    total_artifacts: int
    downloaded: int
    skipped: int
    failed: int
    bytes_downloaded: int


@dataclass(frozen=True)
class BuildResult:
    """构建结果：计划 + 输出 + 错误 + 统计"""

    plan: BuildPlan
    outputs: Tuple[OutputArtifact, ...]
    errors: Tuple[BuildError, ...]
    stats: BuildStats

    @property
    def success(self) -> bool:
        return not self.errors
