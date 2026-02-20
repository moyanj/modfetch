"""
日志模块

使用 loguru 提供统一的日志记录功能。
"""

import os
import sys
from typing import Optional

from loguru import logger


def setup_logger(
    level: Optional[str] = None,
    sink=sys.stdout,
    enqueue: bool = True,
    colorize: bool = True,
) -> None:
    """
    设置日志记录器

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        sink: 输出目标
        enqueue: 是否启用队列（线程安全）
        colorize: 是否启用颜色
    """
    # 从环境变量获取日志级别
    if level is None:
        level = "DEBUG" if os.environ.get("MODFETCH_DEBUG", "0") == "1" else "INFO"

    # 移除默认处理器
    logger.remove()

    # 添加控制台处理器
    logger.add(
        sink=sink,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        enqueue=enqueue,
        level=level,
        colorize=colorize,
        backtrace=(level == "DEBUG"),
        diagnose=(level == "DEBUG"),
    )

    if level == "DEBUG":
        logger.debug("DEBUG 模式已启用")


def get_logger():
    """获取日志记录器实例"""
    return logger


# 导出 logger
__all__ = ["logger", "setup_logger", "get_logger"]
