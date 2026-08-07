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
    """递归解析配置继承（"from" 引用），返回合并后的配置字典

    继承来源可为单个 dict 或 dict 列表，每项含 url + format；
    父配置自身可能再含 "from"，故递归解析。

    合并规则（由 ModFetchConfig.merge_dicts 实现）：
    - dict 值递归合并
    - list 值拼接去重（保持顺序）
    - 其他标量值以子配置（overlay）覆盖父配置（base）
    - "from" 键始终跳过（不参与合并）

    Args:
        config_dict: 当前配置字典（可能含 "from" 键）
        session: aiohttp 会话；缺省时内部创建并在结束时关闭

    Returns:
        合并后的配置字典（不含 "from" 键）

    Raises:
        ValueError: 父配置拉取非 200，或 format 不受支持
    """
    parent_refs = config_dict.get("from")
    if not parent_refs:
        # 无继承引用: 直接返回原配置
        return config_dict

    if isinstance(parent_refs, dict):
        # 单继承简写: 允许 from = {url, format} 而非列表
        parent_refs = [parent_refs]

    parent_dicts = []

    # 未注入 session 时自建并负责关闭（调用方注入则不代为关闭）
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        for ref in parent_refs:
            url = ref.get("url")
            fmt = ref.get("format", "toml")
            if not url:
                # 缺少 url 的引用项跳过
                continue

            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(
                        f"无法加载父配置: {url} (状态码: {response.status})"
                    )

                if fmt == "mrpack":
                    # mrpack 继承: 解析 modrinth.index.json 为配置字典
                    from modfetch.adapters.config.mrpack_resolver import (
                        MrpackResolver,
                    )

                    content_bytes = await response.read()
                    parent_dict = await MrpackResolver.resolve_to_dict(content_bytes)
                else:
                    content = await response.text()
                    # 按 format 选择解析器（toml/json/yaml）
                    if fmt == "toml":
                        parent_dict = toml.loads(content)
                    elif fmt == "json":
                        parent_dict = json.loads(content)
                    elif fmt in ("yaml", "yml"):
                        parent_dict = yaml.safe_load(content)
                    else:
                        raise ValueError(f"不支持的配置格式: {fmt}")

            # 递归解析父配置自身的继承引用
            resolved_parent = await resolve_inheritance(parent_dict, session)
            parent_dicts.append(resolved_parent)
    finally:
        if close_session:
            await session.close()

    # 合并逻辑：从最远的父配置开始合并到当前配置
    #   （多个父配置从左到右叠加，最终以当前配置覆盖）
    final_dict: Dict[str, Any] = {}
    for p_dict in parent_dicts:
        final_dict = ModFetchConfig.merge_dicts(final_dict, p_dict)

    return ModFetchConfig.merge_dicts(final_dict, config_dict)


async def load_with_inheritance(
    config_dict: Dict[str, Any],
    session: Optional[aiohttp.ClientSession] = None,
) -> ModFetchConfig:
    """异步加载带继承逻辑的配置

    先 resolve_inheritance 合并父配置，再转为 ModFetchConfig 领域模型。
    """
    merged_dict = await resolve_inheritance(config_dict, session)
    return ModFetchConfig.from_dict(merged_dict)
