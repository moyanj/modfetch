"""
FastAPI 应用工厂

创建并配置 FastAPI 应用实例，包括:
- CORS 中间件
- REST 路由注册
- WebSocket 路由注册
- JobManager 状态注入
- 静态文件挂载 (生产环境)
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from modfetch.adapters.jobs import JobApplicationService
from modfetch.adapters.modrinth import ModrinthClient
from modfetch.server.routes import router as api_router
from modfetch.server.ws import router as ws_router


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例

    工厂模式：每次调用返回独立应用实例，便于测试隔离与多实例部署。
    组装内容：
        - CORS 中间件：允许前端开发服务器跨域访问
        - app.state.job_manager：全局作业管理器（REST/WS 共享）
        - app.state.catalog：共享 Modrinth 客户端（REST 代理用）
        - REST 路由（/api/*）与 WebSocket 路由（/api/jobs/*/stream）
        - 生产环境静态文件挂载（Vue 构建输出 web/dist）
        - startup/shutdown 生命周期钩子（关闭时释放 catalog 连接）

    Returns:
        FastAPI: 配置好的应用实例
    """
    app = FastAPI(
        title="ModFetch API",
        description="Minecraft 模组下载管理工具 - REST API",
        version="0.2.0",
    )

    # CORS — 允许前端开发服务器访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注入 JobManager 与共享 catalog
    app.state.job_manager = JobApplicationService()
    app.state.catalog = ModrinthClient()

    # 注册 REST 路由
    app.include_router(api_router)

    # 注册 WebSocket 路由
    app.include_router(ws_router)

    # 静态文件挂载 (生产环境 — Vue 构建输出)
    web_dist = Path(__file__).parent.parent / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
        logger.info(f"已挂载静态文件: {web_dist}")
    else:
        logger.debug(f"静态文件目录不存在，跳过挂载: {web_dist}")

    @app.on_event("startup")
    async def startup() -> None:
        logger.info("ModFetch API 服务启动")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await app.state.catalog.close()
        logger.info("ModFetch API 服务关闭")

    return app
