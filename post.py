"""
post 插件（通用版本）

在 ModFetch 打包（PRE_PACKAGE）前，把用户指定的任意多个源目录
整份（递归）复制进每一个版本的下载目录，最终会被带进生成的整合包
（mrpack / zip）的 overrides/ 中。

与 KubeJS 无关，可复制任意文件/目录（kubejs、config、mods 之外的
资源等）。源目录通过 mods.toml 的插件配置指定：

    [plugins.config.post]           # 或 [plugins.config.PostPlugin]
    sources = [
        "kubejs",                       # 相对路径：相对插件文件所在目录
        { src = "./assets", dest = "custom", },   # 指定目标子目录名
        { src = "/abs/path/to/dir", dest = "overrides/x" }, # 绝对路径
    ]

目录结构约定：
    <项目根>/
    ├── post.py            # 本插件
    ├── kubejs/            # 默认源（可省略，仅当未配置 sources 时生效）
    └── mods.toml

它会把这些源目录内容复制到 download_dir 下每个 `{version}-{loader}`
子目录的对应位置，覆盖到整合包的 overrides/，装配时落到
`.minecraft/` 对应路径。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from modfetch.plugins.base import (
    HookType,
    HookContext,
    HookResult,
    ModFetchPlugin,
)


class PostPlugin(ModFetchPlugin):
    """在打包前同步任意源目录到各版本下载目录的通用插件。"""

    name = "post"
    version = "1.1.0"
    description = "打包前自动同步多个自定义源目录到各版本下载目录"
    author = "moyanj"

    # 插件所在目录（作为相对源路径的基准）
    project_root = Path(__file__).resolve().parent

    def register_hooks(self) -> dict:
        return {
            HookType.PRE_PACKAGE: self.on_pre_package,
        }

    def on_pre_package(self, context: HookContext) -> HookResult:
        """在打包开始前，将配置的源目录同步到当前版本下载目录。

        Args:
            context: Hook 上下文，其中 config 提供下载目录与版本信息。

        Returns:
            HookResult: 同步成功返回 success=True。
        """
        sources = self._resolve_sources(context)

        if not sources:
            logger.info("[post] 未配置源目录，跳过")
            return HookResult(success=True)

        # 构造各版本下载目录：download_dir/{version}-{loader}/
        download_root = Path(context.config.output.download_dir)

        results = []
        for loader in _collect_loaders(context.config):
            version_dir = download_root / f"{context.version}-{loader.value}"
            if not version_dir.is_dir():
                logger.debug(f"[post] 版本目录不存在，跳过: {version_dir}")
                continue

            try:
                for src, dest in sources:
                    self._sync_source(src, version_dir, dest)
                results.append(str(version_dir))
                logger.success(f"[post] 源目录已同步到: {version_dir}")
            except OSError as e:
                logger.error(f"[post] 同步 {version_dir} 失败: {e}")
                return HookResult(success=False, error=str(e))

        if not results:
            logger.warning(
                f"[post] 未找到任何匹配的版本下载目录，请检查 download_dir "
                f"({download_root}) 是否已生成"
            )

        return HookResult(data={"synced_dirs": results, "sources": [s[0] for s in sources]})

    def _resolve_sources(
        self, context: HookContext
    ) -> List[tuple]:
        """解析本次要复制的源目录列表。

        优先读取插件配置中的 `sources` 字段；若未配置，则回退到
        项目根下的默认 `kubejs` 目录（保持向后兼容）。

        Args:
            context: Hook 上下文。

        Returns:
            由 (源路径, 目标子目录名或相对路径) 组成的列表。
        """
        config = self._plugin_config(context)

        raw_sources = config.get("sources")
        if not raw_sources:
            default = self.project_root / "kubejs"
            if default.is_dir():
                return [(default, "kubejs")]
            return []

        sources = []
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]

        for item in raw_sources:
            src_path = Path(item) if isinstance(item, (str, os.PathLike)) else None
            dest_name = None

            if isinstance(item, str) and "->" in item:
                # 支持 "src->dest" 紧凑语法
                src_str, dest_str = [s.strip() for s in item.split("->", 1)]
                src_path = Path(src_str)
                dest_name = dest_str.lstrip("./") or None
            elif isinstance(item, dict):
                src_str = item.get("src") or item.get("source")
                if not src_str:
                    logger.warning(f"[post] 源配置缺少 src 字段: {item}")
                    continue
                src_path = Path(src_str)
                dest_name = item.get("dest") or item.get("target")
                if dest_name:
                    dest_name = str(dest_name).lstrip("./") or None
            elif isinstance(item, (str, os.PathLike)):
                src_path = Path(item)

            if src_path is None:
                logger.warning(f"[post] 无法识别的源配置: {item}")
                continue

            # 相对路径统一以项目根为基准
            if not src_path.is_absolute():
                src_path = self.project_root / src_path
            src_path = src_path.resolve()

            if not src_path.exists():
                logger.warning(f"[post] 源目录不存在，跳过: {src_path}")
                continue

            # 默认目标子目录名为源目录的 basename
            if dest_name is None:
                dest_name = src_path.name

            sources.append((src_path, dest_name))

        if not sources:
            logger.warning("[post] 所有配置的源目录均不存在或无效，无内容可同步")
        return sources

    def _plugin_config(self, context: HookContext) -> Dict[str, Any]:
        """从配置文件获取本插件自身的配置段。

        插件配置写在 mods.toml 的 [plugins.config] 下，键名优先
        使用插件 name（'post'），其次使用类名（'PostPlugin'）。

        Args:
            context: Hook 上下文。

        Returns:
            插件配置字典。
        """
        plugin_configs = context.config.plugins.configs or {}
        return plugin_configs.get(self.name) or plugin_configs.get(
            type(self).__name__, {}
        )

    def _sync_source(self, src: Path, version_dir: Path, dest_name: str) -> None:
        """把单个源目录完整复制到版本目录下的目标位置。

        Args:
            src: 源目录。
            version_dir: 版本下载目录。
            dest_name: 目标子目录名或相对路径。
        """
        if src.is_dir():
            target = version_dir / dest_name
            _copy_tree(src, target)
        else:
            # 单文件源：复制到 dest_name 对应的路径
            target = version_dir / dest_name
            os.makedirs(target.parent, exist_ok=True)
            shutil.copy2(src, target)


def _collect_loaders(config) -> list:
    """提取配置中的加载器列表。

    Args:
        config: ModFetchConfig。

    Returns:
        加载器列表。
    """
    if isinstance(config.minecraft.mod_loader, list):
        return config.minecraft.mod_loader
    return [config.minecraft.mod_loader]


def _copy_tree(src: Path, dst: Path) -> None:
    """递归复制源目录到目标目录（目标目录已存在时合并）。

    Args:
        src: 源目录。
        dst: 目标目录。
    """
    os.makedirs(dst, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


plugin_class = PostPlugin