"""CLI 退出码契约测试

契约:
- 成功 → 0
- 配置错误 → 非 0
- 下载失败 → 非 0（当前实现可能为 0 — 已知 bug，xfail 锁定）
"""

import pytest
from click.testing import CliRunner

import modfetch.cli as cli_module
from modfetch.application.validation import ConfigValidationResult
from modfetch.cli import main


async def _fake_validate_remote(self, config, catalog):
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

        result = runner.invoke(main, [config_file(VALID_CONFIG)])
        assert result.exit_code == 0, result.output

    def test_cli_config_error_nonzero(self, runner, config_file):
        """缺少 version → exit code 非 0"""
        result = runner.invoke(main, [config_file(INVALID_CONFIG_NO_VERSION)])
        assert result.exit_code != 0

    def test_cli_config_error_no_content_nonzero(self, runner, config_file):
        """无任何内容条目 → exit code 非 0"""
        result = runner.invoke(main, [config_file(INVALID_CONFIG_NO_CONTENT)])
        assert result.exit_code != 0

    def test_cli_missing_file_nonzero(self, runner):
        """配置文件不存在 → exit code 非 0"""
        result = runner.invoke(main, ["/nonexistent/mods.toml"])
        assert result.exit_code != 0

    def test_cli_dry_run_exit_zero(
        self, runner, config_file, monkeypatch, mock_modrinth, tmp_path
    ):
        """dry-run 模式配置合法 → exit code 0"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            cli_module.ConfigService, "validate_remote", _fake_validate_remote
        )

        result = runner.invoke(main, [config_file(VALID_CONFIG), "--dry-run"])
        assert result.exit_code == 0, result.output

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

        result = runner.invoke(main, [config_file(config)])
        assert result.exit_code != 0
