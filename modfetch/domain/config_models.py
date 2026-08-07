"""
配置领域模型

定义 ModFetch 的所有配置相关数据类（零基础设施依赖）。

与旧 modfetch.models.config 的差异:
- 剥离 aiohttp/yaml/toml/json 导入（继承加载迁入适配层）
- from_dict 不再修改调用方传入的 dict
- from_dict 正确处理 format 为字符串的情况
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


#: 光影加载器 Modrinth slug 集合（oculus 为 iris 的 Forge/NeoForge
#: 移植，二者等价；optifine 独立）。配置声明光影包时，mods 必须
#: 包含其中之一作为光影加载器。
SHADER_LOADER_SLUGS: tuple[str, ...] = ("iris", "oculus", "optifine")


class ModLoader(Enum):
    """模组加载器类型

    枚举值即 Modrinth API 使用的加载器标识符；mod_loader 字段支持
    传入列表，实现同一份配置同时为多个加载器构建。
    """

    FORGE = "forge"
    NEOFORGE = "neoforge"
    FABRIC = "fabric"
    QUILT = "quilt"
    #: 原版 / 无加载器。Modrinth 对数据包、资源包及纯原版兼容版本
    #: 会在 loaders 字段返回 "minecraft"，与服务端/客户端加载器不同，
    #: 需显式收录以免映射时强转失败。仅用于识别版本；不作为配置的
    #: mod_loader 合法值（见 MinecraftConfig.validate 白名单）。
    MINECRAFT = "minecraft"

    @classmethod
    def from_value(cls, value: object) -> Optional["ModLoader"]:
        """宽容解析加载器标识，未知值返回 None 而非抛 ValueError

        Modrinth 的加载器清单持续增加（bukkit/paper/folia/databreaker 等
        服务端或历史加载器），领域层不维护完整清单。对来自 API 的
        loaders 字段采用"命中已识别值则转换、否则忽略"的策略，避免
        任一未知值导致整条版本解析中断；配置层仍走严格路径。
        """
        if not isinstance(value, str):
            return None
        try:
            return cls(value)
        except ValueError:
            return None


class OutputFormat(Enum):
    """输出格式

    决定构建产物的打包格式；OutputConfig.format 可同时指定多种。
    """

    ZIP = "zip"
    MRPACK = "mrpack"


class MrpackMode(Enum):
    """Mrpack 打包模式

    决定 .mrpack 产物中模组的收录方式：download 会把文件实体下载进
    overrides，reference 则仅在 modrinth.index.json 中写入索引引用。
    """

    DOWNLOAD = "download"  # 下载所有模组到 overrides
    REFERENCE = "reference"  # 使用 modrinth.index.json 引用模组（不下载）


class FileType(Enum):
    """文件类型

    标识配置条目的类别，影响打包布局与产物元数据生成。
    """

    MOD = "mod"
    FILE = "file"
    RESOURCEPACK = "resourcepack"
    SHADERPACK = "shaderpack"


@dataclass
class ConditionalEntry:
    """条件配置项基类

    为各配置项提供通用条件字段：
    - only_version: 仅指定的 Minecraft 版本生效
    - feature: 仅指定的功能标签启用时生效（由 --feature 传入）

    计划生成阶段会根据这些条件对条目进行过滤。
    """

    only_version: Optional[Union[str, List[str]]] = None
    feature: Optional[Union[str, List[str]]] = None


@dataclass
class ModEntry(ConditionalEntry):
    """模组配置项

    表示一条模组引用：通过 id（slug）定位 Modrinth 上的项目，
    可附带 version 固定版本、only_version/feature 过滤条件。
    配置中既支持 "sodium" 这种纯字符串，也支持
    { id = "iris", version = "1.7.x", feature = "graphics" } 对象形式。
    """

    id: Optional[str] = None
    slug: Optional[str] = None
    version: Optional[str] = None
    condition: Optional[ConditionalEntry] = None

    def __post_init__(self):
        if not self.id and not self.slug:
            raise ValueError("ModEntry 必须提供 id 或 slug")


@dataclass
class ExtraUrl(ConditionalEntry):
    """额外下载链接配置

    用于收录不通过 Modrinth 检索、直接指定 URL 下载的文件
    （如自定义资源包、专属文件），可附带 sha1 校验与目标文件名。
    """

    url: str = ""
    filename: Optional[str] = None
    type: FileType = FileType.FILE
    sha1: Optional[str] = None
    condition: Optional[ConditionalEntry] = None

    def __post_init__(self):
        if not self.url:
            raise ValueError("ExtraUrl 必须提供 url")
        if self.filename is None:
            # 从 URL 自动提取文件名
            self.filename = self.url.split("/")[-1]


@dataclass
class ParentConfig:
    """父配置引用

    描述一个配置继承来源（本地文件或 URL）。解析阶段会先合并
    from 引用的父配置，再以当前配置覆盖，实现配置复用。
    """

    url: str = ""
    format: str = "toml"  # toml/json/yaml/xml/mrpack

    def __post_init__(self):
        if not self.url:
            raise ValueError("ParentConfig 必须提供 url")
        if self.format not in ["toml", "json", "yaml", "xml", "mrpack"]:
            raise ValueError(f"不支持配置格式: {self.format}")


@dataclass
class MinecraftConfig:
    """Minecraft 相关配置

    核心配置段：声明目标 Minecraft 版本、加载器以及要收录的
    模组/资源包/光影包/额外文件。version 与 mod_loader 均支持
    列表，一次构建可覆盖多版本 × 多加载器组合。
    """

    version: List[str] = field(default_factory=list)
    mod_loader: Union[ModLoader, List[ModLoader]] = ModLoader.FABRIC
    mods: List[Union[str, ModEntry]] = field(default_factory=list)
    resourcepacks: List[Union[str, ModEntry]] = field(default_factory=list)
    shaderpacks: List[Union[str, ModEntry]] = field(default_factory=list)
    extra_urls: List[ExtraUrl] = field(default_factory=list)

    def __post_init__(self):
        if not self.version:
            raise ValueError("MinecraftConfig 必须提供 version")
        if (
            not self.mods
            and not self.resourcepacks
            and not self.shaderpacks
            and not self.extra_urls
        ):
            raise ValueError("MinecraftConfig 必须提供至少一个 模组、资源包或 shader")

    def loaders(self) -> List[ModLoader]:
        """以列表形式返回所有加载器"""
        if isinstance(self.mod_loader, list):
            return self.mod_loader
        return [self.mod_loader]


@dataclass
class OutputConfig:
    """输出配置

    控制产物输出位置与打包格式；format 与 mrpack_modes 均支持
    多选，例如同时产出 zip 与 mrpack。
    """

    download_dir: str = "downloads"
    format: List[OutputFormat] = field(default_factory=lambda: [OutputFormat.ZIP])
    mrpack_modes: List[MrpackMode] = field(
        default_factory=lambda: [MrpackMode.DOWNLOAD]
    )

    def __post_init__(self):
        if not self.download_dir:
            self.download_dir = "downloads"


@dataclass
class MetadataConfig:
    """元数据配置

    整合包的展示信息（名称/版本/描述），会写入产物清单，
    例如 mrpack 的 modrinth.index.json。
    """

    name: str = "ModFetch Pack"
    version: str = "1.0.0"
    description: str = "A modpack generated by ModFetch"


@dataclass
class PluginConfig:
    """插件配置

    enabled 声明要启用的插件名（内置插件或已注册模块），
    configs 为各插件提供可选的配置字典（按插件名索引）。
    """

    enabled: List[str] = field(default_factory=list)
    configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ModFetchConfig:
    """ModFetch 主配置类

    聚合所有配置段（minecraft / output / metadata / plugins）与全局
    选项，是配置解析（from_dict）与构建执行（BuildApplicationService）
    之间统一的数据载体；_raw_config 保留原始字典用于调试与兼容。
    """

    # 必需配置段
    minecraft: MinecraftConfig = field(default_factory=MinecraftConfig)

    # 可选配置段
    output: OutputConfig = field(default_factory=OutputConfig)
    metadata: MetadataConfig = field(default_factory=MetadataConfig)

    # 其他配置
    max_concurrent: int = 5
    max_retries: int = 3
    retry_delay: float = 1.0  # 初始重试延迟（秒）
    verify_ssl: bool = True  # 是否校验 TLS 证书（用于 API 请求与下载）
    features: List[str] = field(default_factory=list)
    parent_configs: List[ParentConfig] = field(default_factory=list)
    plugins: PluginConfig = field(default_factory=PluginConfig)

    # 原始配置字典（用于调试/向后兼容）
    _raw_config: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ModFetchConfig":
        """从字典创建配置对象（不修改传入的 dict）"""
        # 浅拷贝顶层，避免 pop 修改调用方的 dict
        config_dict = dict(config_dict)

        # 保存原始配置
        raw_config = config_dict.copy()

        # 处理父配置引用
        parent_configs = []
        parent_refs = config_dict.pop("from", None)
        if parent_refs:
            if isinstance(parent_refs, dict):
                parent_refs = [parent_refs]
            for ref in parent_refs:
                parent_configs.append(
                    ParentConfig(
                        url=ref.get("url", ""), format=ref.get("format", "toml")
                    )
                )

        # 处理 Minecraft 配置
        mc_dict = config_dict.get("minecraft", {})

        raw_loader = mc_dict.get("mod_loader", "fabric")
        if isinstance(raw_loader, list):
            mod_loader: Union[ModLoader, List[ModLoader]] = [
                ModLoader(loader) for loader in raw_loader
            ]
        else:
            mod_loader = ModLoader(raw_loader)

        minecraft_config = MinecraftConfig(
            version=mc_dict.get("version", []),
            mod_loader=mod_loader,
            mods=cls._parse_mod_entries(mc_dict.get("mods", [])),
            resourcepacks=cls._parse_mod_entries(mc_dict.get("resourcepacks", [])),
            shaderpacks=cls._parse_mod_entries(mc_dict.get("shaderpacks", [])),
            extra_urls=cls._parse_extra_urls(mc_dict.get("extra_urls", [])),
        )

        # 处理输出配置
        output_dict = config_dict.get("output", {})

        # 处理 mrpack_modes
        raw_modes = output_dict.get("mrpack_modes")
        if not raw_modes:
            # 兼容旧的 mrpack_mode
            old_mode = output_dict.get("mrpack_mode", "download")
            mrpack_modes = [MrpackMode(old_mode)]
        else:
            if isinstance(raw_modes, str):
                raw_modes = [raw_modes]
            mrpack_modes = [MrpackMode(m) for m in raw_modes]

        # 处理 format（字符串时归一化为列表）
        raw_format = output_dict.get("format", ["zip"])
        if isinstance(raw_format, str):
            raw_format = [raw_format]

        output_config = OutputConfig(
            download_dir=output_dict.get("download_dir", "downloads"),
            format=[OutputFormat(fmt) for fmt in raw_format],
            mrpack_modes=mrpack_modes,
        )

        # 处理元数据配置
        metadata_dict = config_dict.get("metadata", {})
        metadata_config = MetadataConfig(
            name=metadata_dict.get("name", "ModFetch Pack"),
            version=metadata_dict.get("version", "1.0.0"),
            description=metadata_dict.get("description", ""),
        )

        # 处理插件配置
        plugins_dict = config_dict.get("plugins", {})
        plugin_config = PluginConfig(
            enabled=plugins_dict.get("enabled", []),
            configs=plugins_dict.get("configs", {}),
        )

        return cls(
            minecraft=minecraft_config,
            output=output_config,
            metadata=metadata_config,
            max_concurrent=config_dict.get("max_concurrent", 5),
            max_retries=config_dict.get("max_retries", 3),
            retry_delay=config_dict.get("retry_delay", 1.0),
            features=config_dict.get("features", []),
            parent_configs=parent_configs,
            plugins=plugin_config,
            _raw_config=raw_config,
        )

    @staticmethod
    def _parse_mod_entries(
        entries: List[Any],
    ) -> List[Union[str, ModEntry]]:
        """解析模组条目，支持 slug/id@version 语法"""
        result = []
        for entry in entries:
            if isinstance(entry, str):
                if "@" in entry:
                    identifier, version = entry.split("@", 1)
                    result.append(ModEntry(id=identifier, version=version))
                else:
                    result.append(entry)
            elif isinstance(entry, dict):
                result.append(
                    ModEntry(
                        id=entry.get("id"),
                        slug=entry.get("slug"),
                        version=entry.get("version"),
                        only_version=entry.get("only_version"),
                        feature=entry.get("feature"),
                    )
                )
            else:
                raise ValueError(f"无效的模组条目类型: {type(entry)}")
        return result

    @staticmethod
    def _parse_extra_urls(urls: List[Any]) -> List[ExtraUrl]:
        """解析额外 URL 配置"""
        result = []
        for url_entry in urls:
            if isinstance(url_entry, dict):
                result.append(
                    ExtraUrl(
                        url=url_entry.get("url", ""),
                        filename=url_entry.get("filename"),
                        type=FileType(url_entry.get("type", "file")),
                        sha1=url_entry.get("sha1"),
                        only_version=url_entry.get("only_version"),
                        feature=url_entry.get("feature"),
                    )
                )
            else:
                raise ValueError(f"无效的 extra_urls 条目类型: {type(url_entry)}")
        return result

    @staticmethod
    def merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        """合并两个配置字典（纯函数，供配置继承使用）

        规则:
        - dict 递归合并
        - list 拼接去重（保持顺序）
        - 其他值 overlay 覆盖 base
        - "from" 键始终跳过
        """
        result = base.copy()

        for key, value in overlay.items():
            if key == "from":
                continue

            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ModFetchConfig.merge_dicts(result[key], value)
            elif (
                key in result
                and isinstance(result[key], list)
                and isinstance(value, list)
            ):
                combined = result[key] + value
                seen: List[Any] = []
                for item in combined:
                    if item not in seen:
                        seen.append(item)
                result[key] = seen
            else:
                result[key] = value

        return result

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        if isinstance(self.minecraft.mod_loader, list):
            loader_val: Union[str, List[str]] = [
                loader.value for loader in self.minecraft.mod_loader
            ]
        else:
            loader_val = self.minecraft.mod_loader.value

        return {
            "minecraft": {
                "version": self.minecraft.version,
                "mod_loader": loader_val,
                "mods": self._serialize_mod_entries(self.minecraft.mods),
                "resourcepacks": self._serialize_mod_entries(
                    self.minecraft.resourcepacks
                ),
                "shaderpacks": self._serialize_mod_entries(self.minecraft.shaderpacks),
                "extra_urls": [
                    {
                        "url": url.url,
                        "filename": url.filename,
                        "type": url.type.value,
                        "sha1": url.sha1,
                        "only_version": url.only_version,
                        "feature": url.feature,
                    }
                    for url in self.minecraft.extra_urls
                ],
            },
            "output": {
                "download_dir": self.output.download_dir,
                "format": [fmt.value for fmt in self.output.format],
                "mrpack_modes": [m.value for m in self.output.mrpack_modes],
            },
            "metadata": {
                "name": self.metadata.name,
                "version": self.metadata.version,
                "description": self.metadata.description,
            },
            "max_concurrent": self.max_concurrent,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "features": self.features,
            "from": (
                [
                    {"url": parent.url, "format": parent.format}
                    for parent in self.parent_configs
                ]
                if self.parent_configs
                else None
            ),
            "plugins": {
                "enabled": self.plugins.enabled,
                "configs": self.plugins.configs,
            },
        }

    @staticmethod
    def _serialize_mod_entries(
        entries: List[Union[str, ModEntry]],
    ) -> List[Any]:
        """序列化模组条目"""
        result = []
        for entry in entries:
            if isinstance(entry, str):
                result.append(entry)
            else:
                entry_dict = {}
                if entry.id:
                    entry_dict["id"] = entry.id
                if entry.slug:
                    entry_dict["slug"] = entry.slug
                if entry.version:
                    entry_dict["version"] = entry.version
                if entry.only_version:
                    entry_dict["only_version"] = entry.only_version
                if entry.feature:
                    entry_dict["feature"] = entry.feature
                result.append(entry_dict)
        return result

    def validate(self) -> None:
        """验证配置完整性（本地校验，不涉及远程 API）"""
        if not self.minecraft.version:
            raise ValueError("必须配置 Minecraft 版本")

        if (
            not self.minecraft.mods
            and not self.minecraft.resourcepacks
            and not self.minecraft.shaderpacks
            and not self.minecraft.extra_urls
        ):
            raise ValueError("必须配置至少一个模组、资源包、光影包或额外文件")

        for loader in self.minecraft.loaders():
            if loader not in [
                ModLoader.FORGE,
                ModLoader.NEOFORGE,
                ModLoader.FABRIC,
                ModLoader.QUILT,
            ]:
                raise ValueError(f"无效的 mod_loader: {loader}")

        for group_name, entries in [
            ("模组", self.minecraft.mods),
            ("资源包", self.minecraft.resourcepacks),
            ("光影包", self.minecraft.shaderpacks),
        ]:
            for i, item in enumerate(entries):
                if isinstance(item, ModEntry) and not item.id and not item.slug:
                    raise ValueError(f"{group_name}条目 {i} 必须提供 id 或 slug")
