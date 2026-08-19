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
from typing import Any, Dict, Optional, Set

import aiohttp
import yaml

from modfetch.adapters.config.toml_parser import loads as toml_loads
from modfetch.domain.config_models import ModFetchConfig

#: 远程协议前缀：有此前缀的父配置引用才需要 aiohttp session
_PROTOCOL_PREFIXES = ("http://", "https://")


async def resolve_inheritance(
    config_dict: Dict[str, Any],
    session: Optional[aiohttp.ClientSession] = None,
    *,
    _visited: Optional[Set[str]] = None,
    _base_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """递归解析配置继承（"from" 引用），返回合并后的配置字典

    继承来源可为单个 dict 或 dict 列表，每项含 url + format；
    父配置自身可能再含 "from"，故递归解析。

    合并规则（由 ModFetchConfig.merge_dicts 实现）：
    - dict 值递归合并
    - list 值拼接去重（保持顺序）
    - 其他标量值以子配置（overlay）覆盖父配置（base)
    - "from" 键始终跳过（不参与合并)
    - 合并指令（$delete/$replace/$remove/$override）仅在有继承时有效

    安全性：
    - 循环引用检测：同一引用（归一化后）在当前继承链中出现两次即抛
      ValueError（并列 from 分支各自独立追踪，菱形继承不受影响）
    - file:// 相对路径基于当前配置文件所在目录解析（_base_path），
      链式继承时逐级以父配置所在目录为新基准

    Args:
        config_dict: 当前配置字典（可能含 "from" 键）
        session: aiohttp 会话（仅远程 URL 引用使用）；缺省且存在远程引用时
            内部创建并在结束时关闭
        _visited: 内部参数，当前继承链上已访问的引用标识集合
        _base_path: 内部参数，当前配置文件所在目录（file:// 相对引用基准）

    Returns:
        合并后的配置字典（不含 "from" 键）

    Raises:
        ValueError: 父配置拉取/读取失败（非 200、本地文件不存在）、format
            不受支持、检测到循环引用，或无继承的配置中出现合并指令
    """
    parent_refs = config_dict.get("from")
    if not parent_refs:
        # 无继承引用：合并指令无从生效，检测到即报错（防止误写被静默吞没，
        # 也避免指令字典泄漏到 from_dict 阶段）
        directive_path = _find_merge_directive(config_dict)
        if directive_path is not None:
            raise ValueError(
                f"合并指令仅在通过 from 继承配置时有效: {directive_path}"
            )
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

            # 先解析来源字节；file:// 本地路径基于当前配置文件目录解析
            if url.startswith(_PROTOCOL_PREFIXES):
                ref_identity = url
                parent_base = _base_path
                content_bytes = await _fetch_remote(url, session)
            elif url.startswith("file://"):
                local_path = _resolve_local_path(url, _base_path)
                ref_identity = str(local_path)
                parent_base = local_path.parent
                if not local_path.exists():
                    raise ValueError(f"父配置文件不存在: {local_path}")
                content_bytes = local_path.read_bytes()
            else:
                raise ValueError(
                    f"不支持的父配置来源: {url}（仅支持 file:// 与 http(s)://）"
                )

            # 循环引用检测：引用标识已在当前继承链中出现即判定为循环。
            # 每条并列 from 分支使用独立副本，菱形继承（A→B/C→D）不受影响。
            if ref_identity in (_visited or ()):
                raise ValueError(f"检测到配置继承循环引用: {url}")
            branch_visited = (_visited or set()) | {ref_identity}

            parent_dict = await _parse_content(content_bytes, fmt)
            # 递归解析父配置自身的继承引用（父配置目录成为新的基准路径）
            resolved_parent = await resolve_inheritance(
                parent_dict,
                session,
                _visited=branch_visited,
                _base_path=parent_base,
            )
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


def _find_merge_directive(node: Any, path: str = "") -> Optional[str]:
    """递归扫描配置树，返回第一个 $ 前缀键（合并指令）的路径，无则 None

    用于在无 from 继承的配置中检测误写的合并指令；路径形如
    ``minecraft.mods[0].$remove``，便于用户定位。
    """
    if isinstance(node, dict):
        for key, value in node.items():
            current = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and key.startswith("$"):
                return current
            found = _find_merge_directive(value, current)
            if found is not None:
                return found
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found = _find_merge_directive(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _resolve_local_path(url: str, base_path: Optional[Path]) -> Path:
    """解析 file:// 引用为本地绝对路径

    相对路径（如 file://./base.toml）基于引用方配置文件所在目录
    （base_path）解析，缺省回退到当前工作目录；绝对路径原样使用。
    """
    raw_path = Path(url[len("file://"):])
    if not raw_path.is_absolute():
        base = base_path or Path.cwd()
        return (base / raw_path).resolve()
    return raw_path.resolve()


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
    *,
    base_path: Optional[Path] = None,
) -> ModFetchConfig:
    """异步加载带继承逻辑的配置

    先 resolve_inheritance 合并父配置，再转为 ModFetchConfig 领域模型。

    Args:
        config_dict: 配置字典
        session: aiohttp 会话（远程引用时使用）；缺省时内部创建并关闭
        base_path: 当前配置文件所在目录；file:// 相对引用基于此解析
    """
    merged_dict = await resolve_inheritance(
        config_dict, session, _base_path=base_path
    )
    return ModFetchConfig.from_dict(merged_dict)
