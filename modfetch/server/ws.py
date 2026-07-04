"""
WebSocket 端点

提供 /api/jobs/{job_id}/stream 端点，实时推送任务事件到前端。
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from modfetch.server.jobs import JobManager

router = APIRouter()


@router.websocket("/api/jobs/{job_id}/stream")
async def job_stream(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket 端点 — 流式推送任务事件

    连接后立即开始接收事件，直到任务完成或失败。
    支持多个客户端同时订阅同一任务。
    """
    await websocket.accept()
    logger.info(f"WebSocket 连接: job_id={job_id}")

    # 获取全局 JobManager (由 app.state 设置)
    job_manager: JobManager = websocket.app.state.job_manager

    job = job_manager.get_job(job_id)
    if job is None:
        await websocket.send_json(
            {
                "event": "error",
                "data": {"code": "NOT_FOUND", "message": f"任务 {job_id} 不存在"},
            }
        )
        await websocket.close()
        return

    try:
        async for event in job_manager.subscribe(job_id):
            await websocket.send_json(event)

        # 发送完毕，关闭连接
        await websocket.close()
        logger.info(f"WebSocket 关闭: job_id={job_id}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket 客户端断开: job_id={job_id}")

    except Exception as e:
        logger.error(f"WebSocket 错误: job_id={job_id}, error={e}")
        try:
            await websocket.send_json(
                {
                    "event": "error",
                    "data": {"code": "WS_ERROR", "message": str(e)},
                }
            )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
