"""事件接收适配器

EventSink 端口的一组实现，消费统一的 BuildEvent：
- NullEventSink: 丢弃所有事件（默认/测试）
- LogEventSink: 映射为 loguru 日志（CLI 进度）
- JobEventSink: 翻译为 WebSocket 作业事件流（Web）
- CompositeEventSink: 扇出到多个 sink 并存输出
"""

from modfetch.adapters.events.null_sink import NullEventSink
from modfetch.adapters.events.log_sink import LogEventSink
from modfetch.adapters.events.composite_sink import CompositeEventSink
from modfetch.adapters.events.job_sink import JobEventSink

__all__ = [
    "NullEventSink",
    "LogEventSink",
    "CompositeEventSink",
    "JobEventSink",
]
