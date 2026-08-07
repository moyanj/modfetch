"""日志事件接收器（CLI 进度输出）"""

from loguru import logger

from modfetch.domain.events import BuildEvent, EventType


class LogEventSink:
    """将构建事件映射为 loguru 日志的 EventSink"""

    async def publish(self, event: BuildEvent) -> None:
        data = event.payload
        et = event.event_type

        if et == EventType.CONFIG_VALIDATED:
            logger.info("配置校验通过")
        elif et == EventType.PLAN_CREATED:
            logger.info(
                f"构建计划: {data.get('targets', 0)} 个目标, "
                f"{data.get('artifacts', 0)} 个制品"
            )
        elif et == EventType.DOWNLOAD_STARTED:
            logger.info(f"[开始] 下载: {data.get('filename', '')}")
        elif et == EventType.DOWNLOAD_COMPLETED:
            logger.success(f"[完成] '{data.get('filename', '')}' 下载完成")
        elif et == EventType.DOWNLOAD_FAILED:
            logger.error(
                f"[错误] 下载 '{data.get('filename', '')}' 失败: "
                f"{data.get('error', '')}"
            )
        elif et == EventType.PACKAGE_STARTED:
            logger.info(
                f"正在生成 {data.get('format', '')} "
                f"({data.get('target', '')})..."
            )
        elif et == EventType.PACKAGE_COMPLETED:
            logger.success(f"{data.get('format', '')} 生成成功: {data.get('path', '')}")
        elif et == EventType.PACKAGE_FAILED:
            logger.error(
                f"{data.get('format', '')} 生成失败: {data.get('error', '')}"
            )
        elif et == EventType.BUILD_COMPLETED:
            logger.success("ModFetch 任务完成!")
        elif et == EventType.BUILD_FAILED:
            logger.error(f"构建失败: {data.get('message', '')}")

    async def close(self) -> None:
        pass
