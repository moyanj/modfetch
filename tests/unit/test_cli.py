"""CLI 层单元测试（完全离线）

补充 tests/contract/test_cli_exit_codes.py 未触及的 cli.py 分支：
- 辅助函数: _is_lua_plugin / _handle_cli_errors / _enable_debug
- 插件加载: load_plugins（目录扫描 + 显式加载 + 失败降级）
- 配置内插件: _load_config_and_validate 的 [plugins] enabled 分支
- 子命令: plan（stdout / -o 文件）/ plugins / clean（含 --cache）
- --help / --debug / --link-mode 等选项分支
- __main__ guard

所有 IO 均在 tmp_path 下，远程校验通过 monkeypatch 桩替代，不触网。
"""

import json

import click
import pytest
from click.testing import CliRunner

import modfetch.cli as cli_module
from modfetch.application.validation import ConfigValidationResult, ValidationIssue
from modfetch.cli import main
from modfetch.domain.errors import ModFetchError
from modfetch.plugins import PluginLoader, PluginManager
from modfetch.plugins.lua_loader import LuaPluginLoader

# ---------------------------------------------------------------------------
# 测试常量与公共桩
# ---------------------------------------------------------------------------

VALID_CONFIG = """
[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]

[output]
download_dir = "downloads"
format = ["mrpack"]
"""

#: 最小有效 Python 插件源码（无危险导入，可通过 AST 检查）
PLUGIN_PY_SRC = """\
from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class HelloPlugin(ModFetchPlugin):
    name = "hello_plugin"
    version = "1.0.0"
    description = "测试插件"
    author = "test"

    def register_hooks(self):
        return {}


plugin_class = HelloPlugin
"""

#: 最小 Lua 插件元数据（加载成败不影响 cli.py 分支覆盖）
MIN_LUA_SRC = """\
plugin = {
    name = "hello",
    version = "1.0.0",
    description = "test",
    author = "test"
}
"""


async def _fake_validate_remote(self, config, catalog, features=None):
    """跳过远程校验的测试桩"""
    return ConfigValidationResult(valid=True)


async def _fake_validate_remote_invalid(self, config, catalog, features=None):
    """远程校验失败桩：返回一条 NOT_FOUND issue"""
    issue = ValidationIssue(
        field="minecraft.mods[0]",
        code="NOT_FOUND",
        message="未找到项目: ghost",
        identifier="ghost",
        entry_type="mod",
    )
    return ConfigValidationResult(valid=False, issues=[issue])


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_file(tmp_path):
    """把 TOML 字符串写入临时文件，返回路径"""

    def factory(content: str) -> str:
        path = tmp_path / "mods.toml"
        path.write_text(content)
        return str(path)

    return factory


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_is_lua_plugin_local_and_url(self):
        """_is_lua_plugin: 本地路径与 URL 均应识别 .lua 后缀"""
        assert cli_module._is_lua_plugin("plugin.lua") is True
        assert cli_module._is_lua_plugin("plugin.py") is False
        assert cli_module._is_lua_plugin("https://example.com/x.lua") is True
        assert cli_module._is_lua_plugin("https://example.com/x.py?rev=1") is False
        assert cli_module._is_lua_plugin("file:///tmp/plugin.lua") is True

    async def test_handle_cli_errors_modfetch_error(self):
        """ModFetchError → 转为 click.ClickException（退出码非 0）"""

        @cli_module._handle_cli_errors
        async def boom():
            raise ModFetchError("配置错误")

        with pytest.raises(click.ClickException):
            await boom()

    async def test_handle_cli_errors_generic_exception(self):
        """通用异常 → 包装为 click.ClickException 并记录运行时错误"""

        @cli_module._handle_cli_errors
        async def boom():
            raise RuntimeError("运行时爆炸")

        with pytest.raises(click.ClickException):
            await boom()

    async def test_handle_cli_errors_click_exception_passthrough(self):
        """click.ClickException 原样透传，不二次包装"""

        @cli_module._handle_cli_errors
        async def boom():
            raise click.ClickException("click 异常")

        with pytest.raises(click.ClickException) as excinfo:
            await boom()
        assert "click 异常" in str(excinfo.value)

    async def test_handle_cli_errors_success_path(self):
        """正常返回时不拦截"""

        @cli_module._handle_cli_errors
        async def ok():
            return "ok"

        assert await ok() == "ok"

    def test_enable_debug(self, monkeypatch):
        """_enable_debug: 仅 debug=True 时切换日志级别"""
        calls = []
        monkeypatch.setattr(
            cli_module, "setup_logger", lambda level: calls.append(level)
        )
        cli_module._enable_debug(True)
        assert calls == ["DEBUG"]
        # debug=False 时不应触发 setup_logger
        cli_module._enable_debug(False)
        assert calls == ["DEBUG"]


# ---------------------------------------------------------------------------
# load_plugins（目录扫描 / 显式加载 / 失败降级）
# ---------------------------------------------------------------------------


class TestLoadPlugins:
    async def test_load_plugins_with_dir_scan(self, tmp_path, monkeypatch):
        """目录扫描: 按后缀分发 .py / .lua，非插件后缀走防御分支"""
        pm = PluginManager()
        pl = PluginLoader(pm)
        lua = LuaPluginLoader(pm)
        await lua.initialize()
        try:
            plugin_dir = tmp_path / "plugins"
            plugin_dir.mkdir()
            py_path = plugin_dir / "hello_plugin.py"
            py_path.write_text(PLUGIN_PY_SRC)
            lua_path = plugin_dir / "hello.lua"
            lua_path.write_text(MIN_LUA_SRC)
            # 强制 scan_directory 返回一个 .txt 路径以触发防御 else 分支
            txt_path = plugin_dir / "readme.txt"
            txt_path.write_text("not a plugin")
            monkeypatch.setattr(
                pl, "scan_directory", lambda d: [str(py_path), str(txt_path)]
            )
            monkeypatch.setattr(lua, "scan_directory", lambda d: [str(lua_path)])

            await cli_module.load_plugins(pm, pl, lua, [], str(plugin_dir))
            # .py 插件成功注册；.txt 触发 PluginError 被降级为 warning
            assert pm.get_plugin("hello_plugin") is not None
        finally:
            await lua.shutdown()

    async def test_load_plugins_explicit_py_and_lua(self, tmp_path):
        """显式 --plugin: .lua 走 Lua loader，.py 走 Python loader"""
        pm = PluginManager()
        pl = PluginLoader(pm)
        lua = LuaPluginLoader(pm)
        await lua.initialize()
        try:
            py_path = tmp_path / "hello_plugin.py"
            py_path.write_text(PLUGIN_PY_SRC)
            lua_path = tmp_path / "hello.lua"
            lua_path.write_text(MIN_LUA_SRC)

            await cli_module.load_plugins(pm, pl, lua, [str(py_path), str(lua_path)], None)
            assert pm.get_plugin("hello_plugin") is not None
        finally:
            await lua.shutdown()

    async def test_load_plugins_explicit_failure_degrades(self, tmp_path):
        """显式 --plugin 加载失败 → 记录 error 但不中断"""
        pm = PluginManager()
        pl = PluginLoader(pm)
        lua = LuaPluginLoader(pm)
        await lua.initialize()
        try:
            bad_path = tmp_path / "broken.py"
            # 语法错误 → _validate_plugin_source 抛 PluginLoadError
            bad_path.write_text("this is not valid python !!!")
            await cli_module.load_plugins(pm, pl, lua, [str(bad_path)], None)
            assert pm.list_plugins() == []
        finally:
            await lua.shutdown()


# ---------------------------------------------------------------------------
# _load_config_and_validate（配置内插件 + 远程校验失败）
# ---------------------------------------------------------------------------


class TestLoadConfigAndValidate:
    async def test_config_plugins_builtin_loaded(
        self, tmp_path, monkeypatch, mock_modrinth
    ):
        """[plugins] enabled 含内置插件名 → 从 modfetch.plugins.builtin 加载"""
        config = f"""
[plugins]
enabled = ["filter"]

[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]

[output]
download_dir = "{tmp_path}/downloads"
format = ["mrpack"]
"""
        config_path = tmp_path / "mods.toml"
        config_path.write_text(config)
        monkeypatch.setattr(cli_module.ConfigService, "validate_remote", _fake_validate_remote)

        plugin_loader = PluginLoader(PluginManager())
        cfg = await cli_module._load_config_and_validate(
            str(config_path), [], plugin_loader
        )
        assert cfg.plugins.enabled == ["filter"]

    async def test_config_plugins_third_party_failure_warns(
        self, tmp_path, monkeypatch, mock_modrinth
    ):
        """配置内插件加载失败（内置与第三方都找不到）→ 降级 warning 不中断"""
        config = f"""
[plugins]
enabled = ["nonexistent_plugin_xyz"]

[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]

[output]
download_dir = "{tmp_path}/downloads"
format = ["mrpack"]
"""
        config_path = tmp_path / "mods.toml"
        config_path.write_text(config)
        monkeypatch.setattr(cli_module.ConfigService, "validate_remote", _fake_validate_remote)

        plugin_loader = PluginLoader(PluginManager())
        cfg = await cli_module._load_config_and_validate(
            str(config_path), [], plugin_loader
        )
        # 插件加载失败不影响配置返回
        assert cfg.plugins.enabled == ["nonexistent_plugin_xyz"]

    async def test_remote_validation_failure_raises_click_exception(
        self, tmp_path, monkeypatch, mock_modrinth
    ):
        """远程校验报告 invalid → 抛 click.ClickException"""
        config_path = tmp_path / "mods.toml"
        config_path.write_text(VALID_CONFIG)
        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", _fake_validate_remote_invalid
        )

        plugin_loader = PluginLoader(PluginManager())
        with pytest.raises(click.ClickException) as excinfo:
            await cli_module._load_config_and_validate(
                str(config_path), [], plugin_loader
            )
        assert "未找到项目: ghost" in str(excinfo.value)


# ---------------------------------------------------------------------------
# plan 子命令
# ---------------------------------------------------------------------------


class TestPlanCommand:
    def test_plan_to_stdout(self, runner, config_file, monkeypatch, mock_modrinth, tmp_path):
        """plan 不带 -o → 计划 JSON 打印到 stdout"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli_module.ConfigService, "validate_remote", _fake_validate_remote)

        result = runner.invoke(main, ["plan", "-c", config_file(VALID_CONFIG)])
        assert result.exit_code == 0, result.output
        assert "targets" in result.output

    def test_plan_to_output_file(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """plan -o 文件 → 计划 JSON 写入文件，stdout 为空"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli_module.ConfigService, "validate_remote", _fake_validate_remote)

        out = tmp_path / "plan.json"
        result = runner.invoke(
            main,
            ["plan", "-c", config_file(VALID_CONFIG), "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert "targets" in data

    def test_plan_debug_flag(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """plan --debug → 启用调试日志"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli_module.ConfigService, "validate_remote", _fake_validate_remote)

        result = runner.invoke(
            main, ["plan", "-c", config_file(VALID_CONFIG), "--debug"]
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# plugins 子命令
# ---------------------------------------------------------------------------


class TestPluginsCommand:
    def test_plugins_none_loaded(self, runner):
        """无插件 → 提示没有加载任何插件"""
        result = runner.invoke(main, ["plugins"])
        assert result.exit_code == 0, result.output
        assert "没有加载任何插件" in result.output

    def test_plugins_with_plugin_file(self, runner, tmp_path):
        """--plugin 加载插件 → 列出已加载插件元数据"""
        plugin_file = tmp_path / "hello_plugin.py"
        plugin_file.write_text(PLUGIN_PY_SRC)
        result = runner.invoke(main, ["plugins", "--plugin", str(plugin_file)])
        assert result.exit_code == 0, result.output
        assert "已加载的插件" in result.output
        assert "hello_plugin" in result.output

    def test_plugins_with_plugin_dir(self, runner, tmp_path):
        """--plugin-dir 扫描目录 → 列出目录内插件"""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        (plugin_dir / "hello_plugin.py").write_text(PLUGIN_PY_SRC)
        result = runner.invoke(main, ["plugins", "--plugin-dir", str(plugin_dir)])
        assert result.exit_code == 0, result.output
        assert "hello_plugin" in result.output

    def test_plugins_debug_flag(self, runner):
        """plugins --debug → 启用调试日志"""
        result = runner.invoke(main, ["plugins", "--debug"])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# clean 子命令
# ---------------------------------------------------------------------------


def _clean_config(download_dir) -> str:
    return (
        "[minecraft]\n"
        'version = ["1.21.1"]\n'
        'mod_loader = "fabric"\n'
        'mods = ["sodium"]\n'
        "[output]\n"
        f'download_dir = "{download_dir}"\n'
        'format = ["mrpack"]\n'
    )


class TestCleanCommand:
    def test_clean_removes_workspace_keeps_cache(
        self, runner, config_file, tmp_path
    ):
        """clean 默认只清理打包工作区，保留全局缓存"""
        dl = tmp_path / "downloads"
        (dl / "build" / "1.21.1-fabric").mkdir(parents=True)
        (dl / "build" / "cache").mkdir(parents=True)

        result = runner.invoke(main, ["clean", "-c", config_file(_clean_config(dl))])
        assert result.exit_code == 0, result.output
        assert not (dl / "build" / "1.21.1-fabric").exists()
        assert (dl / "build" / "cache").exists()

    def test_clean_with_cache_flag(self, runner, config_file, tmp_path):
        """clean --cache → 工作区与全局缓存一并清理"""
        dl = tmp_path / "downloads"
        (dl / "build" / "1.21.1-fabric").mkdir(parents=True)
        (dl / "build" / "cache").mkdir(parents=True)

        result = runner.invoke(
            main, ["clean", "-c", config_file(_clean_config(dl)), "--cache"]
        )
        assert result.exit_code == 0, result.output
        assert not (dl / "build" / "1.21.1-fabric").exists()
        assert not (dl / "build" / "cache").exists()

    def test_clean_nothing_to_clean(self, runner, config_file, tmp_path):
        """download_dir 不存在 → 提示无内容可清理"""
        dl = tmp_path / "empty-downloads"
        result = runner.invoke(main, ["clean", "-c", config_file(_clean_config(dl))])
        assert result.exit_code == 0, result.output

    def test_clean_debug_flag(self, runner, config_file, tmp_path):
        """clean --debug → 启用调试日志"""
        dl = tmp_path / "downloads"
        (dl / "build" / "1.21.1-fabric").mkdir(parents=True)
        result = runner.invoke(
            main, ["clean", "-c", config_file(_clean_config(dl)), "--debug"]
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# build 子命令补充选项
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_build_with_debug_and_link_mode_copy(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """build --debug --link-mode copy → 成功且覆盖选项分支"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli_module.ConfigService, "validate_remote", _fake_validate_remote)

        result = runner.invoke(
            main,
            [
                "build",
                "-c",
                config_file(VALID_CONFIG),
                "--debug",
                "--link-mode",
                "copy",
            ],
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# --help / __main__ guard
# ---------------------------------------------------------------------------


class TestMainGuard:
    @pytest.mark.parametrize(
        "args",
        [
            ["--help"],
            ["build", "--help"],
            ["check", "--help"],
            ["plan", "--help"],
            ["plugins", "--help"],
            ["clean", "--help"],
        ],
    )
    def test_cli_help(self, runner, args):
        """所有命令 --help → 退出码 0 且包含 Usage"""
        result = runner.invoke(main, args)
        assert result.exit_code == 0, result.output
        assert "Usage" in result.output

    def test_main_guard_via_runpy(self, monkeypatch):
        """if __name__ == "__main__" → 直接以模块运行触发 main() 帮助输出"""
        import runpy
        import sys

        # runpy.run_module 在目标模块已位于 sys.modules（本文件顶部 import 了
        # modfetch.cli）时会发出 RuntimeWarning；先摘除、结束由 monkeypatch 恢复
        monkeypatch.delitem(sys.modules, "modfetch.cli", raising=False)
        with pytest.raises(SystemExit):
            runpy.run_module("modfetch.cli", run_name="__main__")
