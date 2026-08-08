"""
WebSocket 端点测试（完全离线）

覆盖：正常事件流（含终态关闭）、任务不存在（error 帧 + 关闭）、
订阅异常（WS_ERROR 帧）、客户端中途断开（WebSocketDisconnect 优雅退出）。

说明：TestClient 下客户端断开后服务端 send 不抛异常（starlette 静默丢弃），
故 WebSocketDisconnect 与错误帧发送失败等分支通过直接调用 handler +
假 websocket 对象做单元级覆盖。
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect

from modfetch.adapters.jobs import JobApplicationService
from modfetch.server.ws import job_stream


class FakeWebSocket:
    """假 websocket：可配置 send/close 行为，用于直接驱动 handler"""

    def __init__(self, state, *, send_behavior="ok", close_behavior="ok"):
        self.app = SimpleNamespace(state=state)
        self.accepted = False
        self.sent: list[dict] = []
        self.closed = False
        self.send_behavior = send_behavior
        self.close_behavior = close_behavior

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        if self.send_behavior == "disconnect":
            raise WebSocketDisconnect()
        if self.send_behavior == "error":
            raise RuntimeError("send 失败")
        self.sent.append(data)

    async def close(self) -> None:
        if self.close_behavior == "error":
            raise RuntimeError("close 失败")
        self.closed = True


def test_ws_stream_events_and_close(client, app, make_config_dict):
    """正常流：订阅已终结任务 → 回放事件 → 服务端关闭连接"""
    manager = app.state.job_manager
    job_id = manager.create_job(make_config_dict())
    job = manager.get_job(job_id)

    # 手动广播事件模拟完整流程（无订阅者，broadcast 不触碰跨事件循环队列）
    asyncio.run(
        job.broadcast(
            {
                "event": "job_started",
                "data": {"config_summary": {"mod_count": 1, "loaders": "fabric"}},
            }
        )
    )
    asyncio.run(job.broadcast({"event": "job_complete", "data": {"results": []}}))

    with client.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
        first = ws.receive_json()
        assert first["event"] == "job_started"
        assert first["data"]["config_summary"]["mod_count"] == 1

        second = ws.receive_json()
        assert second["event"] == "job_complete"

        # 任务已终态 → 服务端主动关闭连接
        msg = ws.receive()
        assert msg["type"] == "websocket.close"


def test_ws_job_not_found(client):
    """任务不存在 → error 帧 + 关闭"""
    with client.websocket_connect("/api/jobs/nonexistent/stream") as ws:
        data = ws.receive_json()
        assert data["event"] == "error"
        assert data["data"]["code"] == "NOT_FOUND"
        assert "不存在" in data["data"]["message"]

        msg = ws.receive()
        assert msg["type"] == "websocket.close"


def test_ws_subscribe_error_sends_error_frame(client, app):
    """订阅阶段抛异常 → WS_ERROR 帧 + 关闭"""
    manager = app.state.job_manager
    job_id = manager.create_job({"minecraft": {"mods": ["sodium"]}})

    async def bad_subscribe(job_id: str):
        raise RuntimeError("模拟订阅异常")
        yield  # 不可达：仅使函数成为 async generator

    manager.subscribe = bad_subscribe  # type: ignore[method-assign]

    with client.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
        data = ws.receive_json()
        assert data["event"] == "error"
        assert data["data"]["code"] == "WS_ERROR"
        assert "模拟订阅异常" in data["data"]["message"]

        msg = ws.receive()
        assert msg["type"] == "websocket.close"


def test_ws_client_disconnect(client, app, make_config_dict):
    """客户端中途断开 → 服务端捕获 WebSocketDisconnect 优雅退出（不崩溃）"""
    manager = app.state.job_manager
    job_id = manager.create_job(make_config_dict())

    async def endless_subscribe(job_id: str):
        """持续产出事件；客户端断开后下一次 send 抛 WebSocketDisconnect"""
        seq = 0
        while True:
            seq += 1
            yield {"event": "job_started", "data": {"seq": seq}}
            await asyncio.sleep(0.01)

    manager.subscribe = endless_subscribe  # type: ignore[method-assign]

    with client.websocket_connect(f"/api/jobs/{job_id}/stream") as ws:
        assert ws.receive_json()["event"] == "job_started"

    # 上下文退出 → 客户端已发送关闭帧；留时间给服务端处理断开
    time.sleep(0.1)


# ---------------------------------------------------------------------------
# 直接驱动 handler 的单元测试（覆盖 TestClient 无法触达的分支）
# ---------------------------------------------------------------------------


def test_handler_accepts_and_closes_on_finished_stream():
    """任务已终态 → handler 接受连接、回放事件后关闭"""
    manager = JobApplicationService()
    job_id = manager.create_job({"minecraft": {"mods": ["sodium"]}})
    job = manager.get_job(job_id)
    assert job is not None
    asyncio.run(
        job.broadcast({"event": "job_started", "data": {"config_summary": {}}})
    )
    asyncio.run(job.broadcast({"event": "job_complete", "data": {"results": []}}))

    ws = FakeWebSocket(SimpleNamespace(job_manager=manager))
    asyncio.run(job_stream(ws, job_id))  # type: ignore[arg-type]  # 假 websocket 桩  # type: ignore[arg-type]  # 假 websocket 桩

    assert ws.accepted is True
    assert [event["event"] for event in ws.sent] == ["job_started", "job_complete"]
    assert ws.closed is True


def test_handler_disconnect_branch():
    """客户端断开 → send 抛 WebSocketDisconnect → 优雅退出"""
    manager = JobApplicationService()
    job_id = manager.create_job({"minecraft": {"mods": ["sodium"]}})

    async def subscribe(job_id: str):
        yield {"event": "job_started", "data": {}}
        # 第二次 send 时客户端已断开
        yield {"event": "job_complete", "data": {}}

    manager.subscribe = subscribe  # type: ignore[method-assign]

    ws = FakeWebSocket(
        SimpleNamespace(job_manager=manager), send_behavior="disconnect"
    )
    asyncio.run(job_stream(ws, job_id))  # type: ignore[arg-type]  # 假 websocket 桩

    assert ws.accepted is True
    # 未发送任何帧即退出（WebSocketDisconnect 中断循环）
    assert ws.sent == []


def test_handler_subscribe_error_sends_error_frame():
    """订阅异常 → WS_ERROR 帧 + 关闭"""
    manager = JobApplicationService()
    job_id = manager.create_job({"minecraft": {"mods": ["sodium"]}})

    async def bad_subscribe(job_id: str):
        raise RuntimeError("订阅异常")
        yield  # 不可达：仅使函数成为 async generator

    manager.subscribe = bad_subscribe  # type: ignore[method-assign]

    ws = FakeWebSocket(SimpleNamespace(job_manager=manager))
    asyncio.run(job_stream(ws, job_id))  # type: ignore[arg-type]  # 假 websocket 桩

    assert ws.sent[0]["event"] == "error"
    assert ws.sent[0]["data"]["code"] == "WS_ERROR"
    assert ws.closed is True


def test_handler_error_frame_send_and_close_fail():
    """订阅异常 + 错误帧发送失败 + close 失败 → 内层 except 兜底不崩溃"""
    manager = JobApplicationService()
    job_id = manager.create_job({"minecraft": {"mods": ["sodium"]}})

    async def bad_subscribe(job_id: str):
        raise RuntimeError("订阅异常")
        yield  # 不可达：仅使函数成为 async generator

    manager.subscribe = bad_subscribe  # type: ignore[method-assign]

    ws = FakeWebSocket(
        SimpleNamespace(job_manager=manager),
        send_behavior="error",
        close_behavior="error",
    )
    # 双重故障下 handler 静默兜底，不应抛出异常
    asyncio.run(job_stream(ws, job_id))  # type: ignore[arg-type]  # 假 websocket 桩