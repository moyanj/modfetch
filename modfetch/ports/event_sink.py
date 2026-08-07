"""事件接收端口"""

from typing import Protocol

from modfetch.domain.events import BuildEvent


class EventSink(Protocol):
    """构建事件接收器

    契约约定：事件投递为异步语义，实现负责将 BuildEvent 送达下游
    （日志/作业存储/WebSocket 广播等），投递失败不得中断构建主流程。
    """

    async def publish(self, event: BuildEvent) -> None:
        """发布单个构建事件

        实现期望：
            - 将 event 完整投递到下游（记录/持久化/广播）
            - 投递失败应记录日志而非抛出，避免影响构建主流程
        """
        ...

    async def close(self) -> None:
        """释放底层资源（连接/队列等）；实现必须可重复安全调用"""
        ...
