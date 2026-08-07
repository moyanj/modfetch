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
    """构建生命周期事件类型（value 即 WS 推送的 event 字段）"""

    #: 构建开始
    BUILD_STARTED = "build_started"
    #: 配置已加载
    CONFIG_LOADED = "config_loaded"
    #: 配置已校验
    CONFIG_VALIDATED = "config_validated"
    #: 构建计划已生成
    PLAN_CREATED = "plan_created"
    #: 依赖解析开始
    RESOLVE_STARTED = "resolve_started"
    #: 依赖解析完成
    RESOLVE_COMPLETED = "resolve_completed"
    #: 依赖解析失败
    RESOLVE_FAILED = "resolve_failed"
    #: 单个下载开始
    DOWNLOAD_STARTED = "download_started"
    #: 下载进度更新
    DOWNLOAD_PROGRESS = "download_progress"
    #: 单个下载完成
    DOWNLOAD_COMPLETED = "download_completed"
    #: 单个下载失败
    DOWNLOAD_FAILED = "download_failed"
    #: 打包开始
    PACKAGE_STARTED = "package_started"
    #: 打包完成
    PACKAGE_COMPLETED = "package_completed"
    #: 打包失败
    PACKAGE_FAILED = "package_failed"
    #: 构建整体完成
    BUILD_COMPLETED = "build_completed"
    #: 构建整体失败
    BUILD_FAILED = "build_failed"


@dataclass(frozen=True)
class BuildEvent:
    """统一事件信封

    to_dict() 产出 {"event": <str>, "data": {...}} 格式，
    与现有 WebSocket 消费者兼容。
    """

    job_id: str  #: 所属任务 ID
    event_type: EventType = EventType.BUILD_STARTED  #: 事件类型
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))  #: 事件唯一 ID
    sequence: int = 0  #: 同一任务内的事件序号（单调递增，用于排序/去重）
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )  #: 事件产生时间（UTC ISO8601）
    payload: Dict[str, Any] = field(default_factory=dict)  #: 事件附加数据（随类型而异）

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 WS 兼容信封：payload 展开进 data，与旧消费者字段对齐"""
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
