"""事件接收端口"""

from typing import Protocol

from modfetch.domain.events import BuildEvent


class EventSink(Protocol):
    """构建事件接收器"""

    async def publish(self, event: BuildEvent) -> None:
        ...

    async def close(self) -> None:
        ...
