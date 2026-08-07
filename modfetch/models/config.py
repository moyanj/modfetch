"""向后兼容 shim — 配置模型已迁入 modfetch.domain.config_models

配置继承实现已迁入 modfetch.adapters.config.inheritance。
"""

from modfetch.domain.config_models import *  # noqa: F401,F403
from modfetch.domain.config_models import ModFetchConfig
from modfetch.adapters.config.inheritance import (  # noqa: F401
    load_with_inheritance,
    resolve_inheritance,
)

__all__ = [
    "ModLoader",
    "OutputFormat",
    "MrpackMode",
    "FileType",
    "ConditionalEntry",
    "ModEntry",
    "ExtraUrl",
    "ParentConfig",
    "MinecraftConfig",
    "OutputConfig",
    "MetadataConfig",
    "PluginConfig",
    "ModFetchConfig",
    "load_with_inheritance",
    "resolve_inheritance",
]


# 向后兼容: 旧代码以类方法形式调用 ModFetchConfig.load_with_inheritance
ModFetchConfig.load_with_inheritance = classmethod(
    lambda cls, config_dict, session=None: load_with_inheritance(
        config_dict, session
    )
)
