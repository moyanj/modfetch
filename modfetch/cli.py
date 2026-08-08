"""
CLI 模块（适配层）

职责: 参数解析（子命令风格: build / plan / check / plugins / clean）、
配置加载、依赖组装、错误展示、退出码。
构建编排统一走 BuildApplicationService。
"""

import asyncio
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse

import click
from loguru import logger

from modfetch import __version__
from modfetch.adapters.config import get_config_source, load_with_inheritance
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.application.config_service import ConfigService
from modfetch.application.validation import format_validation_issues
from modfetch.composition import create_build_service
from modfetch.domain.config_models import ModFetchConfig
from modfetch.domain.errors import ModFetchError, PluginError
from modfetch.logger import setup_logger
from modfetch.plugins import PluginManager, PluginLoader
from modfetch.plugins.lua_loader import LuaPluginLoader


async def load_config(config_path: str) -> ModFetchConfig:
    """加载配置文件（含 from 继承链解析）

    按后缀分发到对应 ConfigSource 读取原始字典，再经
    load_with_inheritance 递归合并父配置（file:// 本地或 http(s)://
    远程），最终转为领域模型。

    Raises:
        click.ClickException: 文件不存在，或继承/解析失败
    """
    path = Path(config_path)

    if not path.exists():
        raise click.ClickException(f"配置文件不存在: {config_path}")

    try:
        raw = dict(get_config_source(path).load(path))
        return await load_with_inheritance(raw)
    except ValueError as e:
        raise click.ClickException(str(e)) from e


def _build_options(config, link_mode: str):
    """从配置派生构建执行选项（布局 + 并发 + 物化策略）"""
    from modfetch.application.build_layout import BuildLayout
    from modfetch.application.execute_build import BuildOptions

    return BuildOptions(
        layout=BuildLayout(config.output.download_dir),
        max_concurrent=config.max_concurrent,
        link_mode=link_mode,
    )


def _is_lua_plugin(path: str) -> bool:
    """判断插件路径是否为 Lua 插件（支持本地路径与 URL）"""
    parsed = urlparse(path)
    target = parsed.path if parsed.scheme else path
    return Path(target).suffix == ".lua"


async def load_plugins(
    plugin_manager,
    plugin_loader,
    lua_plugin_manager,
    plugins: list[str],
    plugin_dir: Optional[str],
):
    """加载全部插件（目录扫描 + 显式指定），按语言分发

    职责:
        - 扫描 plugin_dir，将 .py / .lua 文件按后缀分发到对应 loader 加载
        - 加载显式传入的 plugins（本地文件或 URL，按后缀分发）
        - 目录加载失败降级 warning；显式 --plugin 失败记录 error（不中断）

    参数:
        plugin_manager: 插件管理器（已初始化）
        plugin_loader: Python 插件加载器（负责 .py）
        lua_plugin_manager: Lua 插件加载器（负责 .lua）
        plugins: 显式指定的插件路径（--plugin，可多次）
        plugin_dir: 插件目录，递归扫描其中的 .py 与 .lua 文件
    """
    # 扫描插件目录：合并两类 loader 各自扫描到的 .py / .lua 文件，
    # 再按后缀分发到对应 loader 加载
    if plugin_dir:
        plugin_paths = plugin_loader.scan_directory(
            plugin_dir
        ) + lua_plugin_manager.scan_directory(plugin_dir)
        for path in plugin_paths:
            try:
                if path.endswith(".lua"):
                    await lua_plugin_manager.load_from_path(path)
                elif path.endswith(".py"):
                    await plugin_loader.load_from_path(path)
                else:
                    # 两个 scan_directory 只会返回 .py/.lua，此分支为防御兜底
                    raise PluginError("WTF？内存损坏？这是不可能被扫描的")
            except Exception as e:
                logger.warning(f"加载插件 {path} 失败: {e}")

    # 加载指定插件（按语言分发: .lua → Lua loader，其余 → Python loader）
    for plugin_path in plugins:
        try:
            if _is_lua_plugin(plugin_path):
                await lua_plugin_manager.load_from_path(plugin_path)
            else:
                await plugin_loader.load_from_path(plugin_path)
        except Exception as e:
            logger.error(f"加载插件 {plugin_path} 失败: {e}")


async def _load_config_and_validate(
    config_path: str,
    features: list[str],
    plugin_loader,
):
    """加载配置文件 + 本地/远程校验 + 从配置加载插件（Nuitka 环境）

    参数:
        config_path: 配置文件路径（TOML/YAML/JSON）
        features: CLI 传入的功能标签（覆盖配置顶层 features 默认值）
        plugin_loader: Python 插件加载器（负责 .py，用于配置内插件）
    """
    # 加载配置（统一配置边界: 继承合并 → 领域模型 → 本地校验）
    config_service = ConfigService()
    config = await load_config(config_path)
    # 显式传入 CLI 的功能标签做本地校验（含跨字段条件编译判断），
    # 此时 config.features 尚未被 --feature 覆盖，必须显式传参
    config_service.validate_local(config, features or None)
    # 仅在显式传入 -f 时覆盖配置默认 features；未传时保留
    # config.features（如 examples 的 features = ["performance"]）
    if features:
        config.features = features

    # 从配置加载插件（Nuitka 环境使用）
    if config.plugins.enabled:
        logger.info(f"从配置加载插件: {config.plugins.enabled}")
        for plugin_name in config.plugins.enabled:
            try:
                # 尝试作为内置插件加载
                await plugin_loader.load_from_module(
                    f"modfetch.plugins.builtin.{plugin_name}"
                )
            except Exception:
                # 尝试作为第三方插件加载
                try:
                    await plugin_loader.load_from_module(plugin_name)
                except Exception as e:
                    logger.warning(f"从配置加载插件 {plugin_name} 失败: {e}")

    # 远程校验
    async with ModrinthClient() as client:
        report = await config_service.validate_remote(
            config, client, features=features or None
        )
        if not report.is_valid:
            raise click.ClickException(format_validation_issues(report.issues))

    return config


def _handle_cli_errors(fn: Callable[..., Awaitable]):
    """统一把领域异常转成 ClickException，保持 CLI 退出码约定"""

    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ModFetchError as e:
            logger.error(f"配置错误: {e}")
            raise click.ClickException(str(e))
        except click.ClickException:
            raise
        except Exception as e:
            logger.exception(f"运行时错误: {e}")
            raise click.ClickException(f"运行时错误: {e}")

    return wrapper


@asynccontextmanager
async def prepare_context(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
):
    """初始化插件系统 → 加载配置并校验 → 交出 config，退出时释放资源

    职责:
        - 初始化 Python + Lua 双 loader 并加载全部插件
        - 加载配置、本地/远程校验、从配置加载插件
        - 退出时 shutdown Lua 运行时

    参数:
        config_path: 配置文件路径
        features: CLI 功能标签（覆盖配置默认 features）
        plugins: 显式插件路径（--plugin，可多次）
        plugin_dir: 插件目录（递归扫描 .py/.lua）

    yield: 已校验的 config（内部字段完整）
    """
    # 初始化插件系统：Python loader 负责 .py，Lua loader 负责 .lua
    plugin_manager = PluginManager()
    plugin_loader = PluginLoader(plugin_manager)
    lua_plugin_manager = LuaPluginLoader(plugin_manager)
    await lua_plugin_manager.initialize()

    try:
        # 加载插件（目录扫描 + 显式 --plugin，按语言分发）
        await load_plugins(
            plugin_manager, plugin_loader, lua_plugin_manager, plugins, plugin_dir
        )

        # 加载配置并校验（含配置内插件加载）
        config = await _load_config_and_validate(config_path, features, plugin_loader)
        yield config
    finally:
        await lua_plugin_manager.shutdown()


def _create_service(config):
    """从配置创建 BuildApplicationService（DI 组装根）"""
    return create_build_service(
        max_concurrent=config.max_concurrent,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
        verify_ssl=config.verify_ssl,
    )


# ---------------------------------------------------------------------------
# 子命令核心逻辑
# ---------------------------------------------------------------------------


@_handle_cli_errors
async def run_build(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
    link_mode: str,
):
    """执行完整构建（下载 + 打包）"""
    async with prepare_context(config_path, features, plugins, plugin_dir) as config:
        service = _create_service(config)
        try:
            result = await service.execute(
                config,
                job_id="cli",
                options=_build_options(config, link_mode),
            )
        finally:
            # 释放 aiohttp session（catalog/downloader），避免连接池泄漏
            await service.close()

        if result.errors:
            for error in result.errors:
                logger.error(
                    f"[{error.phase}] {error.target.dir_name}: {error.message}"
                )
            raise click.ClickException(f"构建失败: {len(result.errors)} 个错误")

        logger.success(f"完成! 输出 {len(result.outputs)} 个文件")


@_handle_cli_errors
async def run_check(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
):
    """校验配置（不下载/打包），输出配置概要"""
    async with prepare_context(config_path, features, plugins, plugin_dir) as config:
        logger.info("[校验通过] 配置验证完成")
        logger.info(f"  Minecraft 版本: {config.minecraft.version}")

        loaders = config.minecraft.loaders()
        loader_str = ", ".join([loader.value for loader in loaders])
        logger.info(f"  模组加载器: {loader_str}")
        logger.info(f"  模组数量: {len(config.minecraft.mods)}")
        logger.info(f"  资源包数量: {len(config.minecraft.resourcepacks)}")
        logger.info(f"  光影包数量: {len(config.minecraft.shaderpacks)}")


@_handle_cli_errors
async def run_plan(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
    plan_out: Optional[str],
):
    """仅生成构建计划（不下载/打包），可输出到文件或 stdout"""
    async with prepare_context(config_path, features, plugins, plugin_dir) as config:
        service = _create_service(config)
        try:
            result = await service.plan(config, job_id="cli")
            if plan_out:
                with open(plan_out, "w") as f:
                    f.write(result.to_json())
            else:
                click.echo(result.to_json())
        finally:
            await service.close()


@_handle_cli_errors
async def run_plugins(plugins: list[str], plugin_dir: Optional[str]):
    """列出已加载的插件"""
    plugin_manager = PluginManager()
    plugin_loader = PluginLoader(plugin_manager)
    lua_plugin_manager = LuaPluginLoader(plugin_manager)
    await lua_plugin_manager.initialize()

    try:
        await load_plugins(
            plugin_manager, plugin_loader, lua_plugin_manager, plugins, plugin_dir
        )
        loaded_plugins = plugin_manager.list_plugins()
        if loaded_plugins:
            click.echo("已加载的插件:")
            for p in loaded_plugins:
                status = "✓" if p["enabled"] else "✗"
                click.echo(
                    f"  [{status}] {p['name']} v{p['version']} - {p['description']}"
                )
        else:
            click.echo("没有加载任何插件")
    finally:
        await lua_plugin_manager.shutdown()


@_handle_cli_errors
async def run_clean(config_path: str, clean_cache: bool):
    """清理构建工作区（可选 --cache 同时清理全局缓存）"""
    config = await load_config(config_path)

    from modfetch.application.build_layout import BuildLayout, clean_layout

    layout = BuildLayout(config.output.download_dir)
    removed = clean_layout(layout, cache=clean_cache)
    if removed:
        for path in removed:
            logger.info(f"[清理] 已删除: {path}")
    else:
        logger.info("[清理] 无内容可清理")


# ---------------------------------------------------------------------------
# 子命令定义
# ---------------------------------------------------------------------------


def _enable_debug(debug: bool) -> None:
    """按 --debug 切换 loguru 日志级别"""
    if debug:
        setup_logger(level="DEBUG")
        logger.debug("调试模式已启用")


@click.group()
@click.version_option(version=__version__)
def main():
    """ModFetch - Minecraft 模组下载管理工具

    子命令: build / plan / check / plugins / clean
    """


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default="mods.toml",
    show_default=True,
    help="配置文件路径（默认: 当前目录 mods.toml）",
)
@click.option("-f", "--feature", "features", multiple=True, help="启用的功能")
@click.option("--plugin", "plugins", multiple=True, help="加载插件（可多次使用）")
@click.option("--plugin-dir", help="插件目录路径")
@click.option("--debug", is_flag=True, help="启用调试模式")
@click.option(
    "--link-mode",
    type=click.Choice(["link", "copy"]),
    default="link",
    help="物化策略: link(硬链接到缓存,默认) / copy(复制)",
)
def build(config_path, features, plugins, plugin_dir, debug, link_mode):
    """执行完整构建（下载 + 打包）"""
    _enable_debug(debug)
    asyncio.run(
        run_build(
            config_path,
            list(features),
            list(plugins),
            plugin_dir,
            link_mode,
        )
    )


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default="mods.toml",
    show_default=True,
    help="配置文件路径（默认: 当前目录 mods.toml）",
)
@click.option("-f", "--feature", "features", multiple=True, help="启用的功能")
@click.option("--plugin", "plugins", multiple=True, help="加载插件（可多次使用）")
@click.option("--plugin-dir", help="插件目录路径")
@click.option("--debug", is_flag=True, help="启用调试模式")
def check(config_path, features, plugins, plugin_dir, debug):
    """校验配置（不下载、不打包）"""
    _enable_debug(debug)
    asyncio.run(
        run_check(
            config_path,
            list(features),
            list(plugins),
            plugin_dir,
        )
    )


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default="mods.toml",
    show_default=True,
    help="配置文件路径（默认: 当前目录 mods.toml）",
)
@click.option("-f", "--feature", "features", multiple=True, help="启用的功能")
@click.option("--plugin", "plugins", multiple=True, help="加载插件（可多次使用）")
@click.option("--plugin-dir", help="插件目录路径")
@click.option(
    "-o",
    "--output",
    "output",
    default=None,
    help="构建计划输出路径（默认打印到 stdout）",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def plan(config_path, features, plugins, plugin_dir, output, debug):
    """仅生成构建计划（不下载/打包）"""
    _enable_debug(debug)
    asyncio.run(
        run_plan(
            config_path,
            list(features),
            list(plugins),
            plugin_dir,
            output,
        )
    )


@main.command()
@click.option("--plugin", "plugins", multiple=True, help="加载插件（可多次使用）")
@click.option("--plugin-dir", help="插件目录路径")
@click.option("--debug", is_flag=True, help="启用调试模式")
def plugins(plugins, plugin_dir, debug):
    """列出已加载的插件"""
    _enable_debug(debug)
    asyncio.run(run_plugins(list(plugins), plugin_dir))


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default="mods.toml",
    show_default=True,
    help="配置文件路径（默认: 当前目录 mods.toml）",
)
@click.option(
    "--cache",
    "clean_cache",
    is_flag=True,
    help="同时清理全局缓存（默认只清理打包工作区）",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def clean(config_path, clean_cache, debug):
    """清理构建工作区 / 全局缓存"""
    _enable_debug(debug)
    asyncio.run(run_clean(config_path, clean_cache))


if __name__ == "__main__":
    main()
