"""
CLI 模块

命令行接口实现。
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
import toml
from loguru import logger

from modfetch.models import ModFetchConfig
from modfetch.orchestrator import ModFetchOrchestrator
from modfetch.exceptions import ModFetchError
from modfetch.logger import setup_logger


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    path = Path(config_path)

    if not path.exists():
        raise click.ClickException(f"配置文件不存在: {config_path}")

    suffix = path.suffix.lower()

    if suffix == ".toml":
        return toml.load(config_path)
    elif suffix == ".json":
        import json

        return json.loads(path.read_text())
    elif suffix in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(path.read_text())
    else:
        raise click.ClickException(f"不支持的配置文件格式: {suffix}")


async def run_async(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
    list_plugins: bool,
    dry_run: bool = False,
):
    """异步运行"""
    from modfetch.plugins import PluginManager, PluginLoader

    # 初始化插件系统
    plugin_manager = PluginManager()
    plugin_loader = PluginLoader(plugin_manager)

    # 加载插件目录
    if plugin_dir:
        plugin_paths = plugin_loader.scan_directory(plugin_dir)
        for path in plugin_paths:
            try:
                await plugin_loader.load_from_path(path)
            except Exception as e:
                logger.warning(f"加载插件 {path} 失败: {e}")

    # 加载指定插件
    for plugin_path in plugins:
        try:
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
        # 加载配置
        config_dict = load_config(config_path)
        config = ModFetchConfig.from_dict(config_dict)
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

        if dry_run:
            logger.info("[干运行模式] 配置验证通过")
            logger.info(f"  Minecraft 版本: {config.minecraft.version}")
            logger.info(f"  模组加载器: {config.minecraft.mod_loader.value}")
            logger.info(f"  模组数量: {len(config.minecraft.mods)}")
            logger.info(f"  资源包数量: {len(config.minecraft.resourcepacks)}")
            logger.info(f"  光影包数量: {len(config.minecraft.shaderpacks)}")
            return

        # 运行协调器（传入插件管理器）
        orchestrator = ModFetchOrchestrator(config, plugin_manager)
        await orchestrator.run()

        stats = orchestrator.get_stats()
        logger.success(f"完成! 处理了 {stats['processed_mods']} 个模组")

        if stats["skipped"]:
            logger.warning(f"跳过了 {len(stats['skipped'])} 个项目")

    except ModFetchError as e:
        logger.error(f"配置错误: {e}")
        raise click.ClickException(str(e))
    except Exception as e:
        logger.exception(f"运行时错误: {e}")
        raise click.ClickException(f"运行时错误: {e}")


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
    """ModFetch - Minecraft 模组下载管理工具"""
    # 设置日志级别
    if debug:
        setup_logger(level="DEBUG")
        logger.debug("调试模式已启用")

    features = list(feature)
    plugin_list = list(plugins)
    asyncio.run(
        run_async(config, features, plugin_list, plugin_dir, list_plugins, dry_run)
    )


if __name__ == "__main__":
    main()
