"""复合事件接收器（扇出到多个 sink）"""

from typing import List

from modfetch.domain.events import BuildEvent
from modfetch.ports.event_sink import EventSink


class CompositeEventSink:
    """将事件扇出到多个 EventSink"""

    def __init__(self, sinks: List[EventSink]):
        self._sinks = list(sinks)

    async def publish(self, event: BuildEvent) -> None:
        for sink in self._sinks:
            await sink.publish(event)

    async def close(self) -> None:
        for sink in self._sinks:
            await sink.close()
