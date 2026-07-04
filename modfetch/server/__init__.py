"""
ModFetch Server — FastAPI 后端

为 Vue 3 前端提供 REST + WebSocket API，封装 modfetch 编排器。

用法:
    from modfetch.server import create_app
    app = create_app()

    # 或通过命令行:
    # python -m modfetch.server
    # uvicorn modfetch.server.app:create_app --factory --port 8000
"""

from __future__ import annotations

from modfetch.server.app import create_app

__all__ = ["create_app"]
