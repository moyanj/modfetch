"""
CLI 模块（适配层）

职责: 参数解析（子命令风格: build / plan / check / plugins / clean）、
配置加载、依赖组装、错误展示、退出码。
构建编排统一走 BuildApplicationService。
"""

import asyncio
import json
import sys
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
from modfetch.domain.errors import LockError, ModFetchError, PluginError
from modfetch.domain.models import ProjectType
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
        # base_path 使 file:// 相对引用基于配置文件所在目录解析
        return await load_with_inheritance(raw, base_path=path.parent)
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
    locked: bool,
):
    """执行完整构建（下载 + 打包）"""
    async with prepare_context(config_path, features, plugins, plugin_dir) as config:
        service = _create_service(config)
        # 计算 lock 文件路径（配置同目录，名字=配置名去后缀+.lock.json）
        from modfetch.application.build_layout import BuildLayout

        layout = BuildLayout(config.output.download_dir)
        lock_path = str(layout.lock_path_for(config_path))
        try:
            result = await service.execute(
                config,
                job_id="cli",
                options=_build_options(config, link_mode),
                locked=locked,
                lock_path=lock_path,
            )
        finally:
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
async def run_lock(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
):
    """仅生成 lock 文件（不下载/打包）"""
    async with prepare_context(config_path, features, plugins, plugin_dir) as config:
        service = _create_service(config)
        try:
            plan = await service.plan(config, job_id="cli")
            from modfetch.application.build_layout import BuildLayout
            from modfetch.application.lock_service import write_lock

            layout = BuildLayout(config.output.download_dir)
            lock_path = layout.lock_path_for(config_path)
            written = write_lock(lock_path, plan, config, config_path)
            logger.success(f"lock 文件已生成: {written}")
        finally:
            await service.close()


@_handle_cli_errors
async def run_update(
    config_path: str,
    features: list[str],
    plugins: list[str],
    plugin_dir: Optional[str],
):
    """强制重新解析并覆盖 lock，输出变更 diff"""
    from datetime import datetime, timezone

    from modfetch.application.lock_service import (
        LockFile,
        compute_fingerprint,
        diff_locks,
        read_lock,
        write_lock,
    )

    async with prepare_context(config_path, features, plugins, plugin_dir) as config:
        service = _create_service(config)
        try:
            from modfetch.application.build_layout import BuildLayout

            layout = BuildLayout(config.output.download_dir)
            lock_path = layout.lock_path_for(config_path)

            # 读取旧 lock（如果存在）
            old_lock: LockFile | None = None
            try:
                old_lock = read_lock(lock_path)
            except LockError:
                logger.info("[update] 无旧 lock 文件，将全新生成")

            # 重新解析
            new_plan = await service.plan(config, job_id="cli")

            # 构造新 LockFile 用于 diff
            new_lock = LockFile(
                lock_version=1,
                config_fingerprint=compute_fingerprint(config),
                config_path=config_path,
                features=tuple(config.features),
                generated_at=datetime.now(timezone.utc).isoformat(),
                plan=new_plan,
            )

            # 输出 diff
            if old_lock is not None:
                diff = diff_locks(old_lock, new_lock)
                if diff.added:
                    logger.info(f"[update] 新增模组: {', '.join(diff.added)}")
                if diff.removed:
                    logger.info(f"[update] 移除模组: {', '.join(diff.removed)}")
                if diff.changed:
                    for pid, old_url, new_url in diff.changed:
                        logger.info(f"[update] 版本变更: {pid}")
                        logger.info(f"  旧: {old_url}")
                        logger.info(f"  新: {new_url}")
                if not diff.added and not diff.removed and not diff.changed:
                    logger.info("[update] 无变化")

            # 覆盖写 lock
            written = write_lock(lock_path, new_plan, config, config_path)
            logger.success(f"lock 文件已更新: {written}")
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


def _project_type_str(project_type) -> str:
    """归一化项目类型为字符串（兼容枚举与原生字符串）

    search 的 hit 经 map_search_hit 映射后 project_type 为原生
    字符串（如 "mod"/"resourcepack"），但领域模型注解为
    ProjectType 枚举，此处兼容两种形态以免强转报错。
    """
    if isinstance(project_type, ProjectType):
        return project_type.value
    return str(project_type)


def _interactive_available() -> bool:
    """当前 stdin 是否为可交互终端（供交互式命令做降级判断）

    独立成函数便于测试替换（CliRunner 会替换 sys.stdin）。
    """
    return sys.stdin.isatty()


@_handle_cli_errors
async def run_search(
    query: str,
    project_type: Optional[str],
    mc_version: Optional[str],
    loader: Optional[str],
    limit: int,
    as_json: bool,
):
    """在 Modrinth 上搜索模组并展示结果

    不依赖配置文件，直接经 ModrinthClient.search 查询；
    过滤条件（项目类型 / MC 版本 / 加载器）透传给 facets。
    """
    async with ModrinthClient() as client:
        hits = await client.search(
            query,
            project_type=project_type,
            mc_version=mc_version,
            loader=loader,
            limit=limit,
        )

    if not hits:
        # 空结果属于正常业务结果而非错误（CatalogPort 契约），正常退出
        click.echo(f"未找到匹配的模组: {query}")
        return

    if as_json:
        result = [
            {
                "slug": hit.name,
                "title": hit.title,
                "project_type": _project_type_str(hit.project_type),
                "description": hit.description,
                "downloads": hit.downloads,
                "versions": hit.versions,
                "categories": hit.categories,
                "date_created": hit.date_created,
                "date_modified": hit.date_modified,
            }
            for hit in hits
        ]
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return

    click.echo(f"搜索 '{query}' 找到 {len(hits)} 个结果:")
    for hit in hits:
        click.echo(
            f"  {hit.title} ({hit.name}) · {_project_type_str(hit.project_type)}"
            f" · {hit.downloads:,} 下载"
        )
        meta = []
        if hit.categories:
            meta.append(f"分类: {', '.join(hit.categories)}")
        if hit.versions:
            versions = ", ".join(hit.versions[:8])
            suffix = "…" if len(hit.versions) > 8 else ""
            meta.append(f"MC: {versions}{suffix}")
        if hit.date_modified:
            meta.append(f"更新: {hit.date_modified[:10]}")
        if meta:
            click.echo(f"    {' · '.join(meta)}")
        if hit.description:
            click.echo(f"    {hit.description}")


@_handle_cli_errors
async def run_add(
    query: str,
    project_type: Optional[str],
    mc_version: Optional[str],
    loader: Optional[str],
    limit: int,
    config_path: str,
    yes: bool,
):
    """搜索模组 → 用户选择 → 写入配置文件 mods 列表

    流程：Modrinth 搜索 → 编号列表选择（0 取消）→ 以 slug 形式
    追加到配置文件的 minecraft.mods → 重新加载并本地校验。
    ``--yes`` 免交互直选第 1 条（CI/脚本场景）；非 TTY 且未指定
    ``--yes`` 时拒绝交互并提示（避免管道挂起）。
    """
    path = Path(config_path)
    if not path.exists():
        raise click.ClickException(f"配置文件不存在: {config_path}")

    async with ModrinthClient() as client:
        hits = await client.search(
            query,
            project_type=project_type,
            mc_version=mc_version,
            loader=loader,
            limit=limit,
        )

    if not hits:
        # 空结果属于正常业务结果（CatalogPort 契约），正常退出
        click.echo(f"未找到匹配的模组: {query}")
        return

    if yes:
        hit = hits[0]
    else:
        if not _interactive_available():
            # CI/管道下无终端交互，提示改用 --yes 或 --pick，避免挂起
            raise click.ClickException(
                "交互选择需要终端；请使用 --yes 直接添加第一条结果"
            )
        click.echo(f"搜索 '{query}' 找到 {len(hits)} 个结果:")
        for idx, hit in enumerate(hits, start=1):
            click.echo(
                f"  [{idx}] {hit.title} ({hit.name})"
                f" · {_project_type_str(hit.project_type)}"
                f" · {hit.downloads:,} 下载"
            )
            if hit.description:
                click.echo(f"      {hit.description}")
        choice = click.prompt(
            "输入序号选择（0 取消）",
            type=click.IntRange(0, len(hits)),
            default=0,
            show_default=False,
        )
        if choice == 0:
            click.echo("已取消，未修改配置")
            return
        hit = hits[choice - 1]

    from modfetch.adapters.config.writer import add_mod_entry

    added = add_mod_entry(path, hit.name)
    if not added:
        click.echo(f"{hit.name} 已在配置中，跳过")
        return
    click.echo(f"已添加 {hit.title} ({hit.name}) 到 {config_path}")

    # 重新加载并做本地校验（不触网），确保追加后配置仍合法
    config = await load_config(config_path)
    ConfigService().validate_local(config)


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

    子命令: build / plan / check / lock / update / plugins / search / add / clean
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
@click.option(
    "--locked",
    is_flag=True,
    help="按 lock 文件构建（可离线解析、可复现）",
)
def build(config_path, features, plugins, plugin_dir, debug, link_mode, locked):
    """执行完整构建（下载 + 打包）"""
    _enable_debug(debug)
    asyncio.run(
        run_build(
            config_path,
            list(features),
            list(plugins),
            plugin_dir,
            link_mode,
            locked,
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
def lock(config_path, features, plugins, plugin_dir, debug):
    """生成 lock 文件（不下载/打包）"""
    _enable_debug(debug)
    asyncio.run(run_lock(config_path, list(features), list(plugins), plugin_dir))


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
def update(config_path, features, plugins, plugin_dir, debug):
    """强制重新解析并更新 lock 文件，输出变更 diff"""
    _enable_debug(debug)
    asyncio.run(
        run_update(config_path, list(features), list(plugins), plugin_dir)
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
@click.argument("query")
@click.option(
    "--type",
    "project_type",
    type=click.Choice(["mod", "resourcepack", "shader", "datapack"]),
    default=None,
    help="项目类型过滤: mod / resourcepack / shader / datapack",
)
@click.option("--mc-version", help="Minecraft 版本过滤（如 1.21.1）")
@click.option("--loader", help="加载器过滤（如 fabric/forge/neoforge）")
@click.option(
    "--limit",
    default=5,
    show_default=True,
    type=click.IntRange(0, 100),
    help="返回结果条数（0-100）",
)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 格式输出结果")
@click.option("--debug", is_flag=True, help="启用调试模式")
def search(query, project_type, mc_version, loader, limit, as_json, debug):
    """在 Modrinth 上搜索模组"""
    _enable_debug(debug)
    asyncio.run(
        run_search(query, project_type, mc_version, loader, limit, as_json)
    )


@main.command()
@click.argument("query")
@click.option(
    "--type",
    "project_type",
    type=click.Choice(["mod", "resourcepack", "shader", "datapack"]),
    default=None,
    help="项目类型过滤: mod / resourcepack / shader / datapack",
)
@click.option("--mc-version", help="Minecraft 版本过滤（如 1.21.1）")
@click.option("--loader", help="加载器过滤（如 fabric/forge/neoforge）")
@click.option(
    "--limit",
    default=5,
    show_default=True,
    type=click.IntRange(0, 100),
    help="返回结果条数（0-100）",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    default="mods.toml",
    show_default=True,
    help="配置文件路径（默认: 当前目录 mods.toml）",
)
@click.option(
    "--yes",
    is_flag=True,
    help="免交互：直接添加第一条搜索结果（CI/脚本场景）",
)
@click.option("--debug", is_flag=True, help="启用调试模式")
def add(query, project_type, mc_version, loader, limit, config_path, yes, debug):
    """搜索并添加模组到配置文件"""
    _enable_debug(debug)
    asyncio.run(
        run_add(
            query, project_type, mc_version, loader, limit, config_path, yes
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
