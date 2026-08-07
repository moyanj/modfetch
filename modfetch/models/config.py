"""
向后兼容 shim

配置数据类已迁入 modfetch.domain.config_models。
本模块保留配置继承（load_with_inheritance）的 aiohttp 实现，
待阶段 3 迁入 adapters/config/inheritance.py。
"""

import aiohttp
import json
import toml
import yaml
from typing import Any, Dict, Optional

from modfetch.domain.config_models import *  # noqa: F401,F403
from modfetch.domain.config_models import ModFetchConfig

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
]


async def _resolve_inheritance(
    config_dict: Dict[str, Any],
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict[str, Any]:
    """递归解析配置继承（"from" 引用）"""
    parent_refs = config_dict.get("from")
    if not parent_refs:
        return config_dict

    if isinstance(parent_refs, dict):
        parent_refs = [parent_refs]

    parent_dicts = []

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        for ref in parent_refs:
            url = ref.get("url")
            fmt = ref.get("format", "toml")
            if not url:
                continue

            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(
                        f"无法加载父配置: {url} (状态码: {response.status})"
                    )

                if fmt == "mrpack":
                    # 处理 mrpack 继承
                    from modfetch.services.mrpack_resolver import MrpackResolver

                    content_bytes = await response.read()
                    parent_dict = await MrpackResolver.resolve_to_dict(content_bytes)
                else:
                    content = await response.text()
                    if fmt == "toml":
                        parent_dict = toml.loads(content)
                    elif fmt == "json":
                        parent_dict = json.loads(content)
                    elif fmt in ("yaml", "yml"):
                        parent_dict = yaml.safe_load(content)
                    else:
                        raise ValueError(f"不支持的配置格式: {fmt}")

            # 递归解析父配置的继承
            resolved_parent = await _resolve_inheritance(parent_dict, session)
            parent_dicts.append(resolved_parent)
    finally:
        if close_session:
            await session.close()

    # 合并逻辑：从最远的父配置开始合并到当前配置
    final_dict: Dict[str, Any] = {}
    for p_dict in parent_dicts:
        final_dict = ModFetchConfig.merge_dicts(final_dict, p_dict)

    return ModFetchConfig.merge_dicts(final_dict, config_dict)


async def load_with_inheritance(
    config_dict: Dict[str, Any],
    session: Optional[aiohttp.ClientSession] = None,
) -> ModFetchConfig:
    """异步加载带继承逻辑的配置"""
    merged_dict = await _resolve_inheritance(config_dict, session)
    return ModFetchConfig.from_dict(merged_dict)


# 向后兼容: 旧代码以类方法形式调用 ModFetchConfig.load_with_inheritance
ModFetchConfig.load_with_inheritance = classmethod(
    lambda cls, config_dict, session=None: load_with_inheritance(
        config_dict, session
    )
)
