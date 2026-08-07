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

from modfetch.adapters.config import get_config_source
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.application.config_service import ConfigService
from modfetch.application.validation import format_validation_issues
from modfetch.composition import create_build_service
from modfetch.domain.errors import ModFetchError, PluginError
from modfetch.logger import setup_logger
from modfetch.plugins.lua_loader import LuaPluginLoader


def load_config(config_path: str) -> dict:
    """加载配置文件（按后缀分发到对应 ConfigSource）"""
    path = Path(config_path)

    if not path.exists():
        raise click.ClickException(f"配置文件不存在: {config_path}")

    try:
        return dict(get_config_source(path).load(path))
    except ValueError as e:
        raise click.ClickException(str(e)) from e


def _is_lua_plugin(path: str) -> bool:
    """判断插件路径是否为 Lua 插件（支持本地路径与 URL）"""
    parsed = urlparse(path)
    target = parsed.path if parsed.scheme else path
    return Path(target).suffix == ".lua"


async def run_async(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
    list_plugins: bool,
    dry_run: bool = False,
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
    from modfetch.plugins import PluginManager, PluginLoader

    # 初始化插件系统：Python loader 负责 .py，Lua loader 负责 .lua
    plugin_manager = PluginManager()
    plugin_loader = PluginLoader(plugin_manager)
    lua_plugin_manager = LuaPluginLoader(plugin_manager)
    await lua_plugin_manager.initialize()

    try:
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
            config_service.validate_local(config)
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

            # 通过应用服务执行构建
            service = create_build_service(
                max_concurrent=config.max_concurrent,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                verify_ssl=config.verify_ssl,
            )
            try:
                result = await service.execute(config, job_id="cli")
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
@click.version_option(version="0.1.0")
def main(
    config: str,
    feature: tuple,
    plugins: tuple,
    plugin_dir: str,
    list_plugins: bool,
    dry_run: bool,
    debug: bool,
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
        run_async(config, features, plugin_list, plugin_dir, list_plugins, dry_run)
    )


if __name__ == "__main__":
    main()
