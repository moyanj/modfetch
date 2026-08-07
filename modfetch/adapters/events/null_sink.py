"""空事件接收器（默认/测试用）"""

from modfetch.domain.events import BuildEvent


class NullEventSink:
    """丢弃所有事件的 EventSink"""

    async def publish(self, event: BuildEvent) -> None:
        pass

    async def close(self) -> None:
        pass
