"""
配置继承解析

从 models/config.py 迁出。关键变更:
- aiohttp/yaml/toml 等基础设施依赖收敛到本模块（不再位于模型层）
- MrpackResolver 由适配层引入（消除 models→services 分层倒置）
- session 由调用方注入，缺省时内部创建并负责关闭
"""

import json
from typing import Any, Dict, Optional

import aiohttp
import toml
import yaml

from modfetch.domain.config_models import ModFetchConfig


async def resolve_inheritance(
    config_dict: Dict[str, Any],
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict[str, Any]:
    """递归解析配置继承（"from" 引用），返回合并后的配置字典"""
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
                    from modfetch.adapters.config.mrpack_resolver import (
                        MrpackResolver,
                    )

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
            resolved_parent = await resolve_inheritance(parent_dict, session)
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
    merged_dict = await resolve_inheritance(config_dict, session)
    return ModFetchConfig.from_dict(merged_dict)
