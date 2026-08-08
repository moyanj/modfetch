"""
__main__.py 入口测试

覆盖：命令行参数解析（默认/自定义）、loguru 日志级别同步、
uvicorn factory 模式启动调用。uvicorn.run 以 mock 替换，避免真实启动服务。
"""

from __future__ import annotations

from modfetch.server import __main__ as server_main


def test_main_default_args(monkeypatch):
    """无参数启动 → 默认 host/port + factory 模式"""
    calls: dict = {}
    monkeypatch.setattr("sys.argv", ["python -m modfetch.server"])
    monkeypatch.setattr(
        server_main.uvicorn, "run", lambda *a, **kw: calls.update(kw)
    )
    monkeypatch.setattr(
        server_main, "setup_logger", lambda level: calls.update({"loguru_level": level})
    )

    server_main.main()

    assert calls["factory"] is True
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 8000
    assert calls["reload"] is False
    assert calls["log_level"] == "info"
    # loguru 级别由 log_level 大写同步
    assert calls["loguru_level"] == "INFO"


def test_main_custom_args(monkeypatch):
    """自定义 host/port/reload/log-level"""
    calls: dict = {}
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--host", "127.0.0.1",
            "--port", "9000",
            "--reload",
            "--log-level", "debug",
        ],
    )
    monkeypatch.setattr(
        server_main.uvicorn, "run", lambda *a, **kw: calls.update(kw)
    )
    monkeypatch.setattr(
        server_main, "setup_logger", lambda level: calls.update({"loguru_level": level})
    )

    server_main.main()

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9000
    assert calls["reload"] is True
    assert calls["log_level"] == "debug"
    assert calls["loguru_level"] == "DEBUG"