"""
CLI 模块（适配层）

职责: 参数解析、配置加载、依赖组装、错误展示、退出码。
构建编排统一走 BuildApplicationService。
"""

import asyncio
from pathlib import Path
from signal import raise_signal
from typing import Optional
from urllib.parse import urlparse

import click
from loguru import logger

from modfetch import __version__
from modfetch.adapters.config import get_config_source
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.application.config_service import ConfigService
from modfetch.application.validation import format_validation_issues
from modfetch.composition import create_build_service
from modfetch.domain.errors import ModFetchError, PluginError
from modfetch.logger import setup_logger
from modfetch.plugins.lua_loader import LuaPluginLoader
from modfetch.plugins import PluginManager, PluginLoader


def load_config(config_path: str) -> dict:
    """加载配置文件（按后缀分发到对应 ConfigSource）"""
    path = Path(config_path)

    if not path.exists():
        raise click.ClickException(f"配置文件不存在: {config_path}")

    try:
        return dict(get_config_source(path).load(path))
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


async def run_async(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
    list_plugins: bool,
    dry_run: bool = False,
    plan: bool = False,
    plan_out: Optional[str] = None,
    clean_cache: bool = False,
    clean_build: bool = False,
    link_mode: str = "link",
):
    """运行 CLI 主流程（插件加载 + 配置校验 + 构建）

    参数:
        config_path: 配置文件路径（TOML/YAML/JSON）
        features: 启用的功能标签，会覆盖到配置上
        plugins: 显式指定的插件路径（本地文件或 URL，按后缀分发 .py/.lua）
        plugin_dir: 插件目录，递归扫描其中的 .py 与 .lua 文件
        list_plugins: 为真时仅列出现有插件后返回，不执行构建
        dry_run: 干运行，只解析校验配置，不实际下载/打包

    流程:
        初始化插件系统（Python + Lua 双 loader）→ 加载插件 → 加载并校验配置
        → （可选）干运行输出概要 → 通过 BuildApplicationService 执行构建。
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

        # 列出插件
        if list_plugins:
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
            return

        try:
            # 加载配置（统一配置边界: 解析 → 本地校验）
            config_service = ConfigService()
            config = config_service.parse(load_config(config_path))
            # 显式传入 CLI 的功能标签做本地校验（含跨字段条件编译判断），
            # 此时 config.features 尚未被 --feature 覆盖，必须显式传参

            config_service.validate_local(config, features)
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
                report = await config_service.validate_remote(config, client)
                if not report.is_valid:
                    raise click.ClickException(format_validation_issues(report.issues))

            if dry_run:
                logger.info("[干运行模式] 配置验证通过")
                logger.info(f"  Minecraft 版本: {config.minecraft.version}")

                loaders = config.minecraft.loaders()
                loader_str = ", ".join([loader.value for loader in loaders])
                logger.info(f"  模组加载器: {loader_str}")
                logger.info(f"  模组数量: {len(config.minecraft.mods)}")
                logger.info(f"  资源包数量: {len(config.minecraft.resourcepacks)}")
                logger.info(f"  光影包数量: {len(config.minecraft.shaderpacks)}")
                return

            # 清理模式：显式命令（--clean-cache / --clean-build），执行后退出
            if clean_cache or clean_build:
                from modfetch.application.build_layout import (
                    BuildLayout,
                    clean_layout,
                )

                layout = BuildLayout(config.output.download_dir)
                removed = clean_layout(layout, cache=clean_cache)
                if removed:
                    for path in removed:
                        logger.info(f"[清理] 已删除: {path}")
                else:
                    logger.info("[清理] 无内容可清理")
                return

            # 通过应用服务执行构建
            service = create_build_service(
                max_concurrent=config.max_concurrent,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                verify_ssl=config.verify_ssl,
            )
            try:
                if plan:
                    result = await service.plan(config, job_id="cli")
                    if plan_out:
                        with open(plan_out, "w") as f:
                            f.write(result.to_json())
                    else:
                        click.echo(result.to_json())
                    return
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

        except ModFetchError as e:
            logger.error(f"配置错误: {e}")
            raise click.ClickException(str(e))
        except click.ClickException:
            raise
        except Exception as e:
            logger.exception(f"运行时错误: {e}")
            raise click.ClickException(f"运行时错误: {e}")
    finally:
        await lua_plugin_manager.shutdown()


@click.command()
@click.argument("config", type=click.Path(exists=True), default="mods.toml")
@click.option("-f", "--feature", multiple=True, help="启用的功能")
@click.option("--plugin", "plugins", multiple=True, help="加载插件（可多次使用）")
@click.option("--plugin-dir", help="插件目录路径")
@click.option("--list-plugins", is_flag=True, help="列出已加载的插件")
@click.option("--dry-run", is_flag=True, help="干运行模式（只验证配置）")
@click.option("--debug", is_flag=True, help="启用调试模式")
@click.option("--plan", is_flag=True, help="仅生成构建计划")
@click.option("--plan-out", help="构建计划输出路径")
@click.option(
    "--link-mode",
    type=click.Choice(["link", "copy"]),
    default="link",
    help="物化策略: link(硬链接到缓存,默认) / copy(复制)",
)
@click.option("--clean-cache", is_flag=True, help="清理全局缓存后退出")
@click.option("--clean-build", is_flag=True, help="清理打包工作区后退出")
@click.version_option(version=__version__)
def main(
    config: str,
    feature: tuple,
    plugins: tuple,
    plugin_dir: str,
    list_plugins: bool,
    dry_run: bool,
    debug: bool,
    plan: bool,
    plan_out: str,
    link_mode: str,
    clean_cache: bool,
    clean_build: bool,
):
    """ModFetch - Minecraft 模组下载管理工具

    入口点：解析 click 参数（feature/plugin 为可变参数），配置日志后
    交由 run_async 异步执行构建。
    """
    # 设置日志级别
    if debug:
        setup_logger(level="DEBUG")
        logger.debug("调试模式已启用")

    # click 的 tuple 参数转为 list 传给异步主流程
    features = list(feature)
    plugin_list = list(plugins)
    asyncio.run(
        run_async(
            config,
            features,
            plugin_list,
            plugin_dir,
            list_plugins,
            dry_run,
            plan,
            plan_out,
            clean_cache,
            clean_build,
            link_mode,
        )
    )


if __name__ == "__main__":
    main()
