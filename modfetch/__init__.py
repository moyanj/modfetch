from loguru import logger
import sys
import os


def init_logger():
    if os.environ.get("MODFETCH_DEBUG", "0") == "1":
        level = "DEBUG"
        debug_mode = True
    else:
        level = "INFO"
        debug_mode = False
    logger.remove()
    logger.add(
        sink=sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        enqueue=True,
        level=level,
        colorize=True,
        backtrace=debug_mode,
        diagnose=debug_mode,
    )
    if debug_mode:
        logger.debug("DEBUG 模式已启用")
