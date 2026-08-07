"""
统一构建事件协议

CLI 与 Web 共用同一事件信封，消除旧 WS 事件的字段漂移
（total_mods/total、downloaded/completed 并存等问题）。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class EventType(Enum):
    """构建生命周期事件类型"""

    BUILD_STARTED = "build_started"
    CONFIG_LOADED = "config_loaded"
    CONFIG_VALIDATED = "config_validated"
    PLAN_CREATED = "plan_created"
    RESOLVE_STARTED = "resolve_started"
    RESOLVE_COMPLETED = "resolve_completed"
    RESOLVE_FAILED = "resolve_failed"
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    PACKAGE_STARTED = "package_started"
    PACKAGE_COMPLETED = "package_completed"
    PACKAGE_FAILED = "package_failed"
    BUILD_COMPLETED = "build_completed"
    BUILD_FAILED = "build_failed"


@dataclass(frozen=True)
class BuildEvent:
    """统一事件信封

    to_dict() 产出 {"event": <str>, "data": {...}} 格式，
    与现有 WebSocket 消费者兼容。
    """

    job_id: str
    event_type: EventType = EventType.BUILD_STARTED
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event_type.value,
            "data": {
                "job_id": self.job_id,
                "event_id": self.event_id,
                "sequence": self.sequence,
                "timestamp": self.timestamp,
                **self.payload,
            },
        }
