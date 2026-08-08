"""
配置继承解析

从 models/config.py 迁出。关键变更:
- aiohttp/yaml/toml 等基础设施依赖收敛到本模块（不再位于模型层）
- MrpackResolver 由适配层引入（消除 models→services 分层倒置）
- session 由调用方注入，缺省时内部创建并负责关闭（仅在存在远程引用时）
- 父配置来源支持 file:// 本地路径与 http(s):// 远程 URL（与配置文档一致）
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
import yaml

from modfetch.adapters.config.toml_parser import loads as toml_loads
from modfetch.domain.config_models import ModFetchConfig

#: 远程协议前缀：有此前缀的父配置引用才需要 aiohttp session
_PROTOCOL_PREFIXES = ("http://", "https://")


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
    - 其他标量值以子配置（overlay）覆盖父配置（base)
    - "from" 键始终跳过（不参与合并)

    Args:
        config_dict: 当前配置字典（可能含 "from" 键）
        session: aiohttp 会话（仅远程 URL 引用使用）；缺省且存在远程引用时
            内部创建并在结束时关闭

    Returns:
        合并后的配置字典（不含 "from" 键）

    Raises:
        ValueError: 父配置拉取/读取失败（非 200、本地文件不存在），或 format 不受支持
    """
    parent_refs = config_dict.get("from")
    if not parent_refs:
        # 无继承引用: 直接返回原配置
        return config_dict

    if isinstance(parent_refs, dict):
        # 单继承简写: 允许 from = {url, format} 而非列表
        parent_refs = [parent_refs]

    parent_dicts = []

    # 仅当存在远程引用时才需要 aiohttp session（纯 file:// 继承无需建立连接）
    has_remote = any(
        str(ref.get("url", "")).startswith(_PROTOCOL_PREFIXES)
        for ref in parent_refs
    )
    close_session = False
    if has_remote and session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        for ref in parent_refs:
            url = ref.get("url")
            fmt = ref.get("format", "toml")
            if not url:
                # 缺少 url 的引用项跳过
                continue

            if url.startswith(_PROTOCOL_PREFIXES):
                content_bytes = await _fetch_remote(url, session)
            elif url.startswith("file://"):
                # file:// 本地路径：前缀后即相对当前工作目录或绝对路径
                local_path = Path(url[len("file://"):])
                if not local_path.exists():
                    raise ValueError(f"父配置文件不存在: {local_path}")
                content_bytes = local_path.read_bytes()
            else:
                raise ValueError(
                    f"不支持的父配置来源: {url}（仅支持 file:// 与 http(s)://）"
                )

            parent_dict = await _parse_content(content_bytes, fmt)
            # 递归解析父配置自身的继承引用
            resolved_parent = await resolve_inheritance(parent_dict, session)
            parent_dicts.append(resolved_parent)
    finally:
        if close_session and session is not None:
            await session.close()

    # 合并逻辑：从最远的父配置开始合并到当前配置
    #   （多个父配置从左到右叠加，最终以当前配置覆盖）
    final_dict: Dict[str, Any] = {}
    for p_dict in parent_dicts:
        final_dict = ModFetchConfig.merge_dicts(final_dict, p_dict)

    return ModFetchConfig.merge_dicts(final_dict, config_dict)


async def _fetch_remote(
    url: str, session: Optional[aiohttp.ClientSession]
) -> bytes:
    """拉取远程父配置字节内容（session 必为已创建实例）"""
    assert session is not None, "远程引用必须持有 aiohttp session"
    async with session.get(url) as response:
        if response.status != 200:
            raise ValueError(
                f"无法加载父配置: {url} (状态码: {response.status})"
            )
        return await response.read()


async def _parse_content(content_bytes: bytes, fmt: str) -> Dict[str, Any]:
    """按 format 把父配置字节解析为配置字典（mrpack 走 MrpackResolver）

    Raises:
        ValueError: fmt 不受支持
    """
    if fmt == "mrpack":
        # mrpack 继承: 解析 modrinth.index.json 为配置字典
        from modfetch.adapters.config.mrpack_resolver import MrpackResolver

        return await MrpackResolver.resolve_to_dict(content_bytes)

    # 文本格式统一按 UTF-8 解码后解析（toml/json/yaml）
    content = content_bytes.decode("utf-8")
    if fmt == "toml":
        return toml_loads(content)
    if fmt == "json":
        return json.loads(content)
    if fmt in ("yaml", "yml"):
        return yaml.safe_load(content)
    raise ValueError(f"不支持的配置格式: {fmt}")


async def load_with_inheritance(
    config_dict: Dict[str, Any],
    session: Optional[aiohttp.ClientSession] = None,
) -> ModFetchConfig:
    """异步加载带继承逻辑的配置

    先 resolve_inheritance 合并父配置，再转为 ModFetchConfig 领域模型。
    """
    merged_dict = await resolve_inheritance(config_dict, session)
    return ModFetchConfig.from_dict(merged_dict)
