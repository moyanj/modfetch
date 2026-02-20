"""
CLI 模块

命令行接口实现。
"""

import asyncio
import sys
from pathlib import Path

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


async def run_async(config_path: str, features: list[str], dry_run: bool = False):
    """异步运行"""
    try:
        # 加载配置
        config_dict = load_config(config_path)
        config = ModFetchConfig.from_dict(config_dict)
        config.features = features

        if dry_run:
            logger.info("[干运行模式] 配置验证通过")
            logger.info(f"  Minecraft 版本: {config.minecraft.version}")
            logger.info(f"  模组加载器: {config.minecraft.mod_loader.value}")
            logger.info(f"  模组数量: {len(config.minecraft.mods)}")
            logger.info(f"  资源包数量: {len(config.minecraft.resourcepacks)}")
            logger.info(f"  光影包数量: {len(config.minecraft.shaderpacks)}")
            return

        # 运行协调器
        orchestrator = ModFetchOrchestrator(config)
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
@click.option("--dry-run", is_flag=True, help="干运行模式（只验证配置）")
@click.option("--debug", is_flag=True, help="启用调试模式")
@click.version_option(version="0.1.0")
def main(config: str, feature: tuple, dry_run: bool, debug: bool):
    """ModFetch - Minecraft 模组下载管理工具"""
    # 设置日志级别
    if debug:
        setup_logger(level="DEBUG")
        logger.debug("调试模式已启用")

    features = list(feature)
    asyncio.run(run_async(config, features, dry_run))


if __name__ == "__main__":
    main()
