"""事件接收适配器"""

from modfetch.adapters.events.null_sink import NullEventSink
from modfetch.adapters.events.log_sink import LogEventSink
from modfetch.adapters.events.composite_sink import CompositeEventSink

__all__ = ["NullEventSink", "LogEventSink", "CompositeEventSink"]
