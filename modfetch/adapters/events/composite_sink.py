"""复合事件接收器（扇出到多个 sink）"""

from typing import List

from modfetch.domain.events import BuildEvent
from modfetch.ports.event_sink import EventSink


class CompositeEventSink:
    """将事件扇出到多个 EventSink（如 CLI 日志 + Web 作业推送并存）"""

    def __init__(self, sinks: List[EventSink]):
        # 复制列表，防止外部修改影响本实例
        self._sinks = list(sinks)

    async def publish(self, event: BuildEvent) -> None:
        """按注册顺序逐个转发事件（任一 sink 失败即中断）"""
        for sink in self._sinks:
            await sink.publish(event)

    async def close(self) -> None:
        """关闭所有子 sink"""
        for sink in self._sinks:
            await sink.close()
