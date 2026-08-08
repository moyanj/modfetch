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

    minecraft_version: str  #: Minecraft 版本号
    loader: ModLoader  #: 加载器

    @property
    def dir_name(self) -> str:
        """下载目录名（沿用旧命名约定: {version}-{loader}）"""
        return f"{self.minecraft_version}-{self.loader.value}"

    def to_dict(self) -> dict:
        """序列化为纯 dict（枚举转 value，可 JSON 序列化）"""
        return {
            "minecraft_version": self.minecraft_version,
            "loader": self.loader.value,
            "dir_name": self.dir_name,
        }


@dataclass(frozen=True)
class ArtifactCategory:
    """制品类别（决定目标子目录与 mrpack env 标记）"""

    value: str  #: 类别值："mods" / "resourcepacks" / "shaderpacks" / "file"

    @classmethod
    def mods(cls) -> "ArtifactCategory":
        """模组类别"""
        return cls("mods")

    @classmethod
    def resourcepacks(cls) -> "ArtifactCategory":
        """资源包类别"""
        return cls("resourcepacks")

    @classmethod
    def shaderpacks(cls) -> "ArtifactCategory":
        """光影包类别"""
        return cls("shaderpacks")

    @classmethod
    def file(cls) -> "ArtifactCategory":
        """普通文件类别（不归入 mods/resourcepacks 子目录）"""
        return cls("file")

    def to_dict(self) -> str:
        """序列化为纯值（类别本质是字符串包装）"""
        return self.value


@dataclass(frozen=True)
class ResolvedArtifact:
    """一个已解析的待下载制品"""

    project_id: str  #: 来源项目 ID
    project_name: str  #: 来源项目名
    category: ArtifactCategory  #: 制品类别
    filename: str  #: 目标文件名
    url: str  #: 下载地址
    hashes: Dict[str, str]  #: 校验哈希，形如 {"sha1": "...", "sha512": "..."}
    destination: str  #: 相对于版本目录的路径
    target: BuildTarget  #: 所属构建目标
    size: int = 0  #: 文件大小（字节）
    origin: str = "catalog"  #: 来源："catalog"（平台解析）/ "extra_url"（额外URL）
    #: mrpack env 标记，形如 {"client": "required", "server": "required"}
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
            "fileSize": self.size,
        }

    def to_dict(self) -> dict:
        """序列化为纯 dict（可 JSON 序列化）"""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "category": self.category.to_dict(),
            "filename": self.filename,
            "url": self.url,
            "hashes": self.hashes,
            "destination": self.destination,
            "target": self.target.to_dict(),
            "size": self.size,
            "origin": self.origin,
            "environment": self.environment,
            "mrpack_entry": self.to_mrpack_entry(),
        }


@dataclass(frozen=True)
class OutputSpec:
    """输出规格：为某个 target 生成何种格式的包"""

    format: str  #: 输出格式："mrpack" / "zip"
    target: BuildTarget  #: 目标构建目标
    output_name: str  #: 最终文件名（不含扩展名）
    mrpack_mode: str = "download"  #: 仅 mrpack 有效："download" / "reference"

    def to_dict(self) -> dict:
        """序列化为纯 dict（可 JSON 序列化）"""
        return {
            "format": self.format,
            "target": self.target.to_dict(),
            "output_name": self.output_name,
            "mrpack_mode": self.mrpack_mode,
        }


@dataclass(frozen=True)
class BuildPlan:
    """构建计划：目标集合 + 制品集合 + 输出规格集合 + 包元数据"""

    targets: Tuple[BuildTarget, ...]  #: 全部构建目标
    artifacts: Tuple[ResolvedArtifact, ...]  #: 全部待下载制品
    outputs: Tuple[OutputSpec, ...]  #: 全部输出规格
    metadata: Dict[str, str] = field(default_factory=dict)  #: 包元数据（名称/版本等）

    def artifacts_for(self, target: BuildTarget) -> Tuple[ResolvedArtifact, ...]:
        """返回属于指定 target 的制品"""
        return tuple(a for a in self.artifacts if a.target == target)

    def outputs_for(self, target: BuildTarget) -> Tuple[OutputSpec, ...]:
        """返回属于指定 target 的输出规格"""
        return tuple(o for o in self.outputs if o.target == target)

    def to_dict(self) -> dict:
        """序列化为纯 dict（递归转枚举、嵌套对象，可直接 json.dumps）"""
        return {
            "targets": [t.to_dict() for t in self.targets],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "outputs": [o.to_dict() for o in self.outputs],
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """返回 JSON 字符串（供日志/API/持久化消费）"""
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_file(self, path) -> str:
        """将计划序列化为 JSON 并写入指定文件

        Args:
            path: 目标文件路径（str 或 Path）；父目录不存在时自动创建

        Returns:
            写入的绝对路径字符串

        供 CLI（modfetch plan -o）、Web 或外部工具持久化构建计划使用。
        """
        from pathlib import Path

        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")
        return str(target)


@dataclass(frozen=True)
class OutputArtifact:
    """一个已生成的输出文件"""

    path: str  #: 输出文件绝对路径
    format: str  #: 输出格式："mrpack" / "zip"
    target: BuildTarget  #: 所属构建目标
    size: int  #: 文件大小（字节）


@dataclass(frozen=True)
class BuildError:
    """结构化构建错误"""

    code: str  #: 错误码
    message: str  #: 错误消息
    target: BuildTarget  #: 出错的目标
    phase: str  #: 出错阶段："resolve" / "download" / "package"
    context: Dict[str, str] = field(default_factory=dict)  #: 附加上下文


@dataclass(frozen=True)
class BuildStats:
    """构建统计"""

    total_artifacts: int  #: 制品总数
    downloaded: int  #: 成功下载数
    skipped: int  #: 跳过数
    failed: int  #: 失败数
    bytes_downloaded: int  #: 累计下载字节数


@dataclass(frozen=True)
class BuildResult:
    """构建结果：计划 + 输出 + 错误 + 统计"""

    plan: BuildPlan  #: 本次构建的计划
    outputs: Tuple[OutputArtifact, ...]  #: 生成的输出文件
    errors: Tuple[BuildError, ...]  #: 结构化错误列表
    stats: BuildStats  #: 构建统计

    @property
    def success(self) -> bool:
        """是否成功（无错误即成功）"""
        return not self.errors
