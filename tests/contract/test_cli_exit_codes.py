"""CLI 退出码契约测试（子命令风格: build / check）

契约:
- 成功 → 0
- 配置错误 → 非 0
- 下载失败 → 非 0（当前实现可能为 0 — 已知 bug，xfail 锁定）
"""

import pytest
from click.testing import CliRunner

import modfetch.cli as cli_module
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.application.validation import ConfigValidationResult
from modfetch.cli import main


async def _fake_validate_remote(self, config, catalog, features=None):
    """跳过远程校验的测试桩"""
    return ConfigValidationResult(valid=True)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_file(tmp_path):
    """写入配置文件的工厂"""

    def factory(content: str) -> str:
        path = tmp_path / "mods.toml"
        path.write_text(content)
        return str(path)

    return factory


VALID_CONFIG = """
[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]

[output]
download_dir = "downloads"
format = ["mrpack"]
"""

INVALID_CONFIG_NO_VERSION = """
[minecraft]
mod_loader = "fabric"
mods = ["sodium"]
"""

INVALID_CONFIG_NO_CONTENT = """
[minecraft]
version = ["1.21.1"]
"""


class TestExitCodes:
    def test_cli_success_exit_zero(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """正常构建 → exit code 0（离线 mock 全部外部依赖）"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", _fake_validate_remote
        )

        result = runner.invoke(main, ["build", "-c", config_file(VALID_CONFIG)])
        assert result.exit_code == 0, result.output

    def test_cli_config_error_nonzero(self, runner, config_file):
        """缺少 version → exit code 非 0"""
        result = runner.invoke(main, ["build", "-c", config_file(INVALID_CONFIG_NO_VERSION)])
        assert result.exit_code != 0

    def test_cli_config_error_no_content_nonzero(self, runner, config_file):
        """无任何内容条目 → exit code 非 0"""
        result = runner.invoke(main, ["build", "-c", config_file(INVALID_CONFIG_NO_CONTENT)])
        assert result.exit_code != 0

    def test_cli_missing_file_nonzero(self, runner):
        """配置文件不存在 → exit code 非 0"""
        result = runner.invoke(main, ["build", "-c", "/nonexistent/mods.toml"])
        assert result.exit_code != 0

    def test_cli_check_resolves_from_inheritance(
        self, runner, config_file, monkeypatch, tmp_path
    ):
        """CLI 应合并 file:// 父配置，而非仅解析当前子配置。"""
        parent = tmp_path / "parent.toml"
        parent.write_text(
            "[minecraft]\n"
            'version = ["1.21.1"]\n'
            'mod_loader = "fabric"\n'
            'mods = ["sodium"]\n',
            encoding="utf-8",
        )
        child = (
            f'from = [{{ url = "{parent.as_uri()}", format = "toml" }}]\n'
            "[minecraft]\n"
            'mods = ["modmenu"]\n'
        )
        captured = {}

        async def capture_remote(self, config, catalog, features=None):
            captured["versions"] = config.minecraft.version
            captured["mods"] = config.minecraft.mods
            return ConfigValidationResult(valid=True)

        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", capture_remote
        )

        result = runner.invoke(main, ["check", "-c", config_file(child)])

        assert result.exit_code == 0, result.output
        assert captured["versions"] == ["1.21.1"]
        assert captured["mods"] == ["sodium", "modmenu"]

    def test_cli_check_exit_zero(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """check 模式配置合法 → exit code 0"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", _fake_validate_remote
        )

        result = runner.invoke(main, ["check", "-c", config_file(VALID_CONFIG)])
        assert result.exit_code == 0, result.output

    def test_cli_no_feature_keeps_config_default(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """未传 -f 时保留配置文件里的默认 features（不空列表覆盖）"""
        monkeypatch.chdir(tmp_path)
        captured = {}

        async def fake_validate_remote(self, config, catalog, features=None):
            captured["config_features"] = list(config.features)
            captured["arg_features"] = features
            return ConfigValidationResult(valid=True)

        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", fake_validate_remote
        )

        config = f"""
features = ["performance"]

[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]

[output]
download_dir = "{tmp_path}/dl"
format = ["mrpack"]
"""

        result = runner.invoke(main, ["check", "-c", config_file(config)])
        assert result.exit_code == 0, result.output
        # 未覆盖 config.features；校验也未显式覆盖成空列表
        assert captured["config_features"] == ["performance"]
        assert captured["arg_features"] is None

    def test_cli_feature_overrides_config_default(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """显式传 -f 时覆盖配置默认 features"""
        monkeypatch.chdir(tmp_path)
        captured = {}

        async def fake_validate_remote(self, config, catalog, features=None):
            captured["config_features"] = list(config.features)
            captured["arg_features"] = features
            return ConfigValidationResult(valid=True)

        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", fake_validate_remote
        )

        config = f"""
features = ["performance"]

[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]

[output]
download_dir = "{tmp_path}/dl"
format = ["mrpack"]
"""

        result = runner.invoke(
            main, ["check", "-c", config_file(config), "-f", "shaders"]
        )
        assert result.exit_code == 0, result.output
        assert captured["config_features"] == ["shaders"]
        assert captured["arg_features"] == ["shaders"]

    def test_cli_download_failure_nonzero(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """下载失败 → exit code 非 0"""
        monkeypatch.chdir(tmp_path)
        config = f"""
[minecraft]
version = ["1.21.1"]
mod_loader = "fabric"
mods = ["sodium"]
extra_urls = [{{ url = "file:///nonexistent/ghost.jar" }}]

[output]
download_dir = "{tmp_path}/dl"
format = ["mrpack"]
"""

        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", _fake_validate_remote
        )

        result = runner.invoke(main, ["build", "-c", config_file(config)])
        assert result.exit_code != 0

    def test_cli_search_exit_zero(self, runner, mock_modrinth):
        """search 命中结果 → exit code 0"""
        result = runner.invoke(main, ["search", "sodium"])
        assert result.exit_code == 0, result.output

    def test_cli_search_empty_exit_zero(self, runner, monkeypatch):
        """search 无结果 → exit code 0（空列表是正常业务结果，非错误）"""

        async def _empty_search(self, query, **kwargs):
            return []

        monkeypatch.setattr(ModrinthClient, "search", _empty_search)
        result = runner.invoke(main, ["search", "ghost-mod"])
        assert result.exit_code == 0, result.output
