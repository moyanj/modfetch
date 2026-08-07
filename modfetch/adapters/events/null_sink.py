"""空事件接收器（默认/测试用）"""

from modfetch.domain.events import BuildEvent


class NullEventSink:
    """丢弃所有事件的 EventSink（默认占位 / 测试用）

    publish/close 均为空操作，避免无 sink 时的空指针。
    """

    async def publish(self, event: BuildEvent) -> None:
        pass

    async def close(self) -> None:
        pass
