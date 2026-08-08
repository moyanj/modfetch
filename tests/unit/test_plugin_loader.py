"""插件加载器（loader.py）单元测试

覆盖 PluginLoader 的路径分发、文件/目录/模块/URL 加载、
AST 源码校验（_validate_plugin_source）、模块注册与目录扫描。
全部离线：URL 加载通过伪造 aiohttp 会话完成。
"""

import sys
import types
from pathlib import Path

import pytest

from modfetch.domain.errors import ModFetchError
from modfetch.plugins.base import ModFetchPlugin, PluginManager
from modfetch.plugins.loader import PluginLoadError, PluginLoader

# 一个合法的插件源码：继承 ModFetchPlugin 并实现 register_hooks
PLUGIN_SOURCE = '''
from modfetch.plugins.base import ModFetchPlugin, HookType, HookContext, HookResult


class MyTestPlugin(ModFetchPlugin):
    name = "my_test_plugin"
    version = "1.0.0"
    description = "test plugin"
    author = "test"

    def register_hooks(self):
        return {HookType.CONFIG_LOADED: self.on_config_loaded}

    def on_config_loaded(self, context: HookContext) -> HookResult:
        return HookResult()


plugin_class = MyTestPlugin
'''


@pytest.fixture
def plugin_manager() -> PluginManager:
    return PluginManager()


@pytest.fixture
def loader(plugin_manager: PluginManager) -> PluginLoader:
    return PluginLoader(plugin_manager)


def _write_plugin(tmp_path: Path, name: str = "my_plugin.py") -> Path:
    """把合法插件源码写入临时目录"""
    path = tmp_path / name
    path.write_text(PLUGIN_SOURCE, encoding="utf-8")
    return path


class FakeResponse:
    """伪造 aiohttp 响应：async 上下文管理器 + text()"""

    def __init__(self, status: int = 200, text: str = ""):
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self) -> str:
        return self._text


class FakeSession:
    """伪造 aiohttp 会话：async 上下文管理器 + get()"""

    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url: str):
        return self._response


class TestPluginLoadError:
    def test_is_modfetch_error(self):
        """PluginLoadError 属于 ModFetchError 体系"""
        assert issubclass(PluginLoadError, ModFetchError)


class TestLoguruFallback:
    def test_fallback_to_stdlib_logging(self, monkeypatch):
        """loguru 不可导入时回退到标准库 logging"""
        import importlib
        import logging
        import sys

        import modfetch.plugins
        import modfetch.plugins.loader as original_loader

        # 置空 loguru 触发 ImportError，随后重新导入模块
        monkeypatch.setitem(sys.modules, "loguru", None)
        monkeypatch.delitem(sys.modules, "modfetch.plugins.loader")
        mod = importlib.import_module("modfetch.plugins.loader")
        assert isinstance(mod.logger, logging.Logger)
        assert mod.logger.name == "modfetch"
        # 手动恢复：re-import 会同时改写 sys.modules 与包属性
        # modfetch.plugins.loader，monkeypatch 只还原前者，需显式还原后者
        sys.modules["modfetch.plugins.loader"] = original_loader
        setattr(modfetch.plugins, "loader", original_loader)


class TestLoadFromFile:
    async def test_success(self, loader, plugin_manager, tmp_path):
        """从 .py 文件加载插件成功"""
        path = _write_plugin(tmp_path)
        assert await loader.load_from_path(str(path)) is True
        assert plugin_manager.get_plugin("my_test_plugin") is not None

    async def test_missing_file(self, loader, tmp_path):
        """文件不存在抛 PluginLoadError（直接调用内部方法，绕过路径分发）"""
        with pytest.raises(PluginLoadError, match="插件文件不存在"):
            await loader._load_from_file(str(tmp_path / "nope.py"), None)

    async def test_wrong_suffix(self, loader, tmp_path):
        """非 .py 后缀抛 PluginLoadError"""
        path = tmp_path / "plugin.txt"
        path.write_text("x = 1", encoding="utf-8")
        with pytest.raises(PluginLoadError, match="不支持的文件格式"):
            await loader.load_from_path(str(path))

    async def test_syntax_error(self, loader, tmp_path):
        """源码语法错误抛 PluginLoadError"""
        path = tmp_path / "bad.py"
        path.write_text("def broken(:\n", encoding="utf-8")
        with pytest.raises(PluginLoadError, match="插件源码语法错误"):
            await loader.load_from_path(str(path))

    async def test_spec_none(self, loader, tmp_path, monkeypatch):
        """spec_from_file_location 返回 None 时抛 PluginLoadError"""
        path = _write_plugin(tmp_path)
        monkeypatch.setattr(
            "modfetch.plugins.loader.importlib.util.spec_from_file_location",
            lambda *a, **k: None,
        )
        with pytest.raises(PluginLoadError, match="无法创建模块规范"):
            await loader.load_from_path(str(path))

    async def test_spec_loader_none(self, loader, tmp_path, monkeypatch):
        """spec.loader 为 None 时抛 PluginLoadError"""

        class FakeSpec:
            loader = None

        path = _write_plugin(tmp_path)
        monkeypatch.setattr(
            "modfetch.plugins.loader.importlib.util.spec_from_file_location",
            lambda *a, **k: FakeSpec(),
        )
        with pytest.raises(PluginLoadError, match="无法创建模块规范"):
            await loader.load_from_path(str(path))

    async def test_duplicate_load(self, loader, plugin_manager, tmp_path):
        """同一插件文件重复加载：第二次因同名插件已注册返回 False"""
        path = _write_plugin(tmp_path)
        assert await loader.load_from_path(str(path)) is True
        assert await loader.load_from_path(str(path)) is False


class TestLoadFromDirectory:
    async def test_init_file(self, loader, plugin_manager, tmp_path):
        """目录含 __init__.py 时优先加载它"""
        dir_path = tmp_path / "plugindir"
        dir_path.mkdir()
        (dir_path / "__init__.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
        assert await loader.load_from_path(str(dir_path)) is True
        assert plugin_manager.get_plugin("my_test_plugin") is not None

    async def test_first_py_file(self, loader, plugin_manager, tmp_path):
        """无 __init__.py 时加载第一个 .py 文件"""
        dir_path = tmp_path / "plugindir"
        dir_path.mkdir()
        (dir_path / "a.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
        assert await loader.load_from_path(str(dir_path)) is True
        assert plugin_manager.get_plugin("my_test_plugin") is not None

    async def test_missing_dir(self, loader, tmp_path):
        """目录不存在抛 PluginLoadError（直接调用内部方法，绕过路径分发）"""
        with pytest.raises(PluginLoadError, match="插件目录不存在"):
            await loader._load_from_directory(str(tmp_path / "nope"), None)

    async def test_no_py_files(self, loader, tmp_path):
        """目录中没有 .py 文件抛 PluginLoadError"""
        dir_path = tmp_path / "empty"
        dir_path.mkdir()
        with pytest.raises(PluginLoadError, match="目录中没有找到 Python 文件"):
            await loader.load_from_path(str(dir_path))


class TestLoadFromModule:
    async def test_success(self, loader, plugin_manager):
        """从真实内置模块加载插件"""
        assert await loader.load_from_module("modfetch.plugins.builtin.filter") is True
        assert plugin_manager.get_plugin("filter") is not None

    async def test_dispatch_via_load_from_path(self, loader, plugin_manager):
        """load_from_path 对模块名分发到 load_from_module"""
        assert (
            await loader.load_from_path("modfetch.plugins.builtin.filter") is True
        )
        assert plugin_manager.get_plugin("filter") is not None

    async def test_already_in_sys_modules(self, loader, plugin_manager, monkeypatch):
        """模块已在 sys.modules 时直接复用"""

        module = types.ModuleType("fake_plugin_module")

        class FakePlugin(ModFetchPlugin):
            name = "fake_plugin"

            def register_hooks(self):
                return {}

        setattr(module, "FakePlugin", FakePlugin)
        monkeypatch.setitem(sys.modules, "fake_plugin_module", module)
        assert await loader.load_from_module("fake_plugin_module") is True
        assert plugin_manager.get_plugin("fake_plugin") is not None

    async def test_import_error(self, loader):
        """模块无法导入抛 PluginLoadError"""
        with pytest.raises(PluginLoadError, match="无法导入模块"):
            await loader.load_from_module("modfetch.plugins.nonexistent_module_xyz")


class TestLoadFromUrl:
    async def test_success(self, loader, plugin_manager, monkeypatch):
        """URL 下载源码并加载插件"""
        monkeypatch.setattr(
            "modfetch.plugins.loader.aiohttp.ClientSession",
            lambda: FakeSession(FakeResponse(status=200, text=PLUGIN_SOURCE)),
        )
        assert await loader.load_from_path("http://example.com/plugin.py") is True
        assert plugin_manager.get_plugin("my_test_plugin") is not None

    async def test_no_filename_fallback(self, loader, plugin_manager, monkeypatch):
        """URL 路径无文件名时回退到 plugin.py"""
        monkeypatch.setattr(
            "modfetch.plugins.loader.aiohttp.ClientSession",
            lambda: FakeSession(FakeResponse(status=200, text=PLUGIN_SOURCE)),
        )
        assert await loader.load_from_path("http://example.com/") is True
        assert plugin_manager.get_plugin("my_test_plugin") is not None

    async def test_unsupported_scheme(self, loader):
        """非 http/https 协议抛 PluginLoadError（直接调用内部方法，绕过路径分发）"""
        with pytest.raises(PluginLoadError, match="不支持的 URL 协议"):
            await loader._load_from_url("ftp://example.com/plugin.py", None)

    async def test_http_error(self, loader, monkeypatch):
        """HTTP 非 200 抛 PluginLoadError"""
        monkeypatch.setattr(
            "modfetch.plugins.loader.aiohttp.ClientSession",
            lambda: FakeSession(FakeResponse(status=404, text="")),
        )
        with pytest.raises(PluginLoadError, match="无法下载插件: HTTP 404"):
            await loader.load_from_path("http://example.com/plugin.py")

    async def test_client_error(self, loader, monkeypatch):
        """aiohttp 网络错误抛 PluginLoadError"""
        import aiohttp

        class ErrorSession(FakeSession):
            def get(self, url: str):
                raise aiohttp.ClientError("connection refused")

        monkeypatch.setattr(
            "modfetch.plugins.loader.aiohttp.ClientSession",
            lambda: ErrorSession(FakeResponse()),
        )
        with pytest.raises(PluginLoadError, match="下载插件失败"):
            await loader.load_from_path("http://example.com/plugin.py")

    async def test_temp_file_cleaned(self, loader, plugin_manager, monkeypatch, tmp_path):
        """加载完成后临时文件被清理"""
        temp_path = tmp_path / "downloaded_plugin.py"
        unlinked = []

        class FakeTempFile:
            def __init__(self, *args, **kwargs):
                self.name = str(temp_path)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def write(self, content: str):
                temp_path.write_text(content, encoding="utf-8")

        monkeypatch.setattr(
            "modfetch.plugins.loader.aiohttp.ClientSession",
            lambda: FakeSession(FakeResponse(status=200, text=PLUGIN_SOURCE)),
        )
        monkeypatch.setattr(
            "modfetch.plugins.loader.tempfile.NamedTemporaryFile", FakeTempFile
        )
        monkeypatch.setattr(
            "modfetch.plugins.loader.os.unlink", lambda p: unlinked.append(p)
        )

        assert await loader.load_from_path("http://example.com/plugin.py") is True
        assert str(temp_path) in unlinked

    async def test_temp_file_unlink_oserror(
        self, loader, plugin_manager, monkeypatch, tmp_path
    ):
        """临时文件 unlink 抛 OSError 时静默忽略（finally 兜底）"""
        temp_path = tmp_path / "downloaded_plugin.py"

        class FakeTempFile:
            def __init__(self, *args, **kwargs):
                self.name = str(temp_path)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def write(self, content: str):
                temp_path.write_text(content, encoding="utf-8")

        monkeypatch.setattr(
            "modfetch.plugins.loader.aiohttp.ClientSession",
            lambda: FakeSession(FakeResponse(status=200, text=PLUGIN_SOURCE)),
        )
        monkeypatch.setattr(
            "modfetch.plugins.loader.tempfile.NamedTemporaryFile", FakeTempFile
        )
        monkeypatch.setattr(
            "modfetch.plugins.loader.os.unlink",
            lambda p: (_ for _ in ()).throw(OSError("permission denied")),
        )

        # unlink 失败不应影响插件加载结果
        assert await loader.load_from_path("http://example.com/plugin.py") is True


class TestValidatePluginSource:
    def test_valid_source(self, loader):
        """合法源码返回 True"""
        assert loader._validate_plugin_source("x = 1") is True

    def test_syntax_error(self, loader):
        """语法错误抛 PluginLoadError"""
        with pytest.raises(PluginLoadError, match="插件源码语法错误"):
            loader._validate_plugin_source("def broken(:")

    def test_dangerous_import(self, loader, monkeypatch):
        """import subprocess 触发危险导入警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        assert loader._validate_plugin_source("import subprocess") is True
        assert any("subprocess" in w for w in warnings)

    def test_dangerous_import_from(self, loader, monkeypatch):
        """from subprocess import run 触发危险导入警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        assert loader._validate_plugin_source("from subprocess import run") is True
        assert any("subprocess" in w for w in warnings)

    def test_dangerous_importlib(self, loader, monkeypatch):
        """import importlib 触发危险导入警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        assert loader._validate_plugin_source("import importlib") is True
        assert any("importlib" in w for w in warnings)

    def test_dangerous_sys_modules_import_from(self, loader, monkeypatch):
        """from sys.modules import x 触发危险导入警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        assert loader._validate_plugin_source("from sys.modules import x") is True
        assert any("sys.modules" in w for w in warnings)

    def test_dangerous_os_system_import_from(self, loader, monkeypatch):
        """from os.system import x 触发危险导入警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        assert loader._validate_plugin_source("from os.system import x") is True
        assert any("os.system" in w for w in warnings)

    def test_dangerous_builtins(self, loader, monkeypatch):
        """import eval/exec/compile/__import__ 均触发警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        source = "import eval\nimport exec\nimport compile\nimport __import__"
        assert loader._validate_plugin_source(source) is True
        assert len(warnings) == 4

    def test_safe_import_no_warning(self, loader, monkeypatch):
        """普通导入（os/json）不触发警告"""
        warnings = []
        monkeypatch.setattr(
            "modfetch.plugins.loader.logger.warning", lambda msg: warnings.append(msg)
        )
        assert loader._validate_plugin_source("import os\nimport json") is True
        assert warnings == []


class TestRegisterPluginFromModule:
    def test_success(self, loader, plugin_manager):
        """模块含有效插件类时注册成功"""
        module = types.ModuleType("fake_module")

        class FakePlugin(ModFetchPlugin):
            name = "fake_plugin"

            def register_hooks(self):
                return {}

        setattr(module, "FakePlugin", FakePlugin)
        assert loader._register_plugin_from_module(module, None) is True
        assert plugin_manager.get_plugin("fake_plugin") is not None

    def test_no_plugin_class(self, loader):
        """模块中没有插件类抛 PluginLoadError"""
        module = types.ModuleType("fake_module")
        setattr(module, "x", 1)
        with pytest.raises(PluginLoadError, match="模块中没有找到有效的插件类"):
            loader._register_plugin_from_module(module, None)

    def test_empty_name_class(self, loader):
        """插件类 name 为空时被过滤，抛 PluginLoadError"""
        module = types.ModuleType("fake_module")

        class EmptyNamePlugin(ModFetchPlugin):
            name = ""

            def register_hooks(self):
                return {}

        setattr(module, "EmptyNamePlugin", EmptyNamePlugin)
        with pytest.raises(PluginLoadError, match="模块中没有找到有效的插件类"):
            loader._register_plugin_from_module(module, None)


class TestScanDirectory:
    def test_missing_dir(self, loader, tmp_path):
        """目录不存在返回空列表"""
        assert loader.scan_directory(str(tmp_path / "nope")) == []

    def test_finds_py_files(self, loader, tmp_path):
        """递归找到所有 .py 文件"""
        dir_path = tmp_path / "plugins"
        dir_path.mkdir()
        (dir_path / "a.py").write_text("x = 1", encoding="utf-8")
        (dir_path / "b.py").write_text("x = 2", encoding="utf-8")
        sub = dir_path / "sub"
        sub.mkdir()
        (sub / "c.py").write_text("x = 3", encoding="utf-8")
        paths = loader.scan_directory(str(dir_path))
        assert len(paths) == 3

    def test_skips_pycache_and_tests(self, loader, tmp_path):
        """跳过 __pycache__ 与 test_ 前缀文件"""
        dir_path = tmp_path / "plugins"
        dir_path.mkdir()
        (dir_path / "a.py").write_text("", encoding="utf-8")
        (dir_path / "test_b.py").write_text("", encoding="utf-8")
        pycache = dir_path / "__pycache__"
        pycache.mkdir()
        (pycache / "c.py").write_text("", encoding="utf-8")
        paths = loader.scan_directory(str(dir_path))
        assert [Path(p).name for p in paths] == ["a.py"]


class TestLoadMultiple:
    async def test_mixed_results(self, loader, plugin_manager, tmp_path):
        """批量加载：单个失败不中断其余，结果按路径汇总"""
        path = _write_plugin(tmp_path)
        missing = str(tmp_path / "missing.py")
        results = await loader.load_multiple([str(path), missing])
        assert results == {str(path): True, missing: False}

    async def test_runtime_error_in_plugin(self, loader, plugin_manager, tmp_path):
        """插件模块级抛异常时该路径记为失败"""
        bad = tmp_path / "bad.py"
        bad.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        results = await loader.load_multiple([str(bad)])
        assert results == {str(bad): False}