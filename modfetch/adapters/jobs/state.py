"""
作业状态（内存实现）

JobState 维护事件订阅者队列与事件折叠快照:
- broadcast() 推送事件到所有订阅者并折叠到状态
- 事件历史供晚订阅者回放
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class JobStats:
    """任务统计

    从事件流折叠得到的进度指标（download 完成后由 stats_update 更新）。
    """

    total_mods: int = 0
    resolved: int = 0
    downloaded: int = 0
    failed: int = 0
    bytes_downloaded: int = 0


@dataclass
class JobResultItem:
    """任务结果项

    单个构建产物摘要，供 API 响应与前端列表展示。
    """

    filename: str
    path: str
    size: int
    format: str
    mc_version: str
    loader: str


@dataclass
class JobErrorItem:
    """任务错误项

    结构化的单条错误（code/message/context），随 job_failed 折叠入状态。
    """

    code: str
    message: str
    context: Optional[dict[str, object]] = None


@dataclass
class JobState:
    """
    任务状态

    每个任务维护一组订阅者队列 (asyncio.Queue)，事件通过 broadcast()
    推送到所有订阅者。WebSocket 端点通过 subscribe() 创建新队列并消费事件。

    状态机：
        pending --start_job--> running --job_complete--> completed
                                +--job_failed----------> failed
      - job_started 事件将 pending 置为 running
      - job_complete / job_failed 事件终结运行（phase 复位为 idle）
      - 当前无显式取消/中断路径：任务随进程生命周期运行至终态
    """

    id: str
    status: str  # pending | running | completed | failed
    phase: str  # idle | resolve | download | package
    stats: JobStats
    config_dict: dict[str, object]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: list[JobResultItem] = field(default_factory=list)
    errors: list[JobErrorItem] = field(default_factory=list)
    event_history: list[dict[str, object]] = field(default_factory=list)

    # 事件订阅
    _subscribers: list[asyncio.Queue[dict[str, object]]] = field(
        default_factory=list
    )
    # 后台任务
    _task: Optional[asyncio.Task[None]] = None
    # 当前版本/加载器
    current_version: str = ""
    current_loader: str = ""

    @property
    def duration_ms(self) -> int:
        """任务持续时间 (毫秒)"""
        if self.started_at is None:
            return 0
        end = self.completed_at or datetime.now(timezone.utc)
        return int((end - self.started_at).total_seconds() * 1000)

    async def broadcast(self, event: dict[str, object]) -> None:
        """将事件推送到所有订阅者队列"""
        self._record_event(event)
        self._apply_event(event)
        for queue in self._subscribers:
            await queue.put(event)

    def _record_event(self, event: dict[str, object]) -> None:
        """记录任务事件历史，供晚订阅的客户端回放。"""
        self.event_history.append(event)
        if len(self.event_history) > 512:
            self.event_history.pop(0)

    def _apply_event(self, event: dict[str, object]) -> None:
        """将事件折叠到当前任务状态快照。

        幂等地把事件反映到 status/phase/stats/results/errors 上：
        - job_started → running
        - phase_change → 阶段切换
        - stats_update → 刷新进度统计
        - job_complete → completed + 结果列表
        - job_failed → failed + 错误列表（去重）
        """
        event_type = event.get("event")
        data = event.get("data")
        if not isinstance(data, dict):
            # 无 data 负载的事件不折叠
            return

        if event_type == "job_started":
            # 状态转移: pending → running
            self.status = "running"
            return

        if event_type == "phase_change":
            # 阶段切换: idle ↔ resolve / download / package
            phase = data.get("phase")
            if isinstance(phase, str):
                self.phase = phase
            return

        if event_type == "stats_update":
            # 折叠进度快照（缺失字段保留原值）
            total = _safe_int(data.get("total"), self.stats.total_mods)
            completed = _safe_int(data.get("completed"), self.stats.downloaded)
            failed = _safe_int(data.get("failed"), self.stats.failed)
            bytes_downloaded = _safe_int(
                data.get("bytes_downloaded"), self.stats.bytes_downloaded
            )
            self.stats.total_mods = total
            self.stats.downloaded = completed
            self.stats.failed = failed
            self.stats.bytes_downloaded = bytes_downloaded
            return

        if event_type == "resolve_complete":
            # 仅累计 resolved 计数（resolve 无独立进度总量）
            self.stats.resolved += 1
            return

        if event_type == "job_complete":
            # 状态转移: running → completed，阶段复位，写入结果
            self.status = "completed"
            self.phase = "idle"
            self.results = _parse_results(data.get("results"))
            return

        if event_type == "job_failed":
            # 状态转移: running → failed，阶段复位，追加去重后的错误
            self.status = "failed"
            self.phase = "idle"
            error = _parse_error(data.get("error"))
            if error is not None and not _has_error(self.errors, error):
                self.errors.append(error)

    def to_response_dict(self) -> dict[str, object]:
        """转换为 API 响应字典

        输出与前端约定的 JSON 结构（字段名/空值语义与原接口一致）。
        """

        def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
            if dt is None:
                return None
            return dt.isoformat()

        return {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "stats": {
                "total_mods": self.stats.total_mods,
                "resolved": self.stats.resolved,
                "downloaded": self.stats.downloaded,
                "failed": self.stats.failed,
                "bytes_downloaded": self.stats.bytes_downloaded,
            },
            "results": (
                [
                    {
                        "filename": r.filename,
                        "path": r.path,
                        "size": r.size,
                        "format": r.format,
                        "mc_version": r.mc_version,
                        "loader": r.loader,
                    }
                    for r in self.results
                ]
                if self.results
                else None
            ),
            "errors": (
                [
                    {
                        "code": e.code,
                        "message": e.message,
                        "context": e.context,
                    }
                    for e in self.errors
                ]
                if self.errors
                else None
            ),
            "started_at": fmt_dt(self.started_at),
            "completed_at": fmt_dt(self.completed_at),
        }


def _safe_int(value: object, default: int = 0) -> int:
    """安全转换整数。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_results(value: object) -> list[JobResultItem]:
    """从事件数据解析结果列表。"""
    if not isinstance(value, list):
        return []

    results: list[JobResultItem] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        path = item.get("path")
        fmt = item.get("format")
        mc_version = item.get("mc_version")
        loader = item.get("loader")
        if not all(
            isinstance(field, str)
            for field in (filename, path, fmt, mc_version, loader)
        ):
            continue
        results.append(
            JobResultItem(
                filename=filename,
                path=path,
                size=_safe_int(item.get("size")),
                format=fmt,
                mc_version=mc_version,
                loader=loader,
            )
        )
    return results


def _parse_error(value: object) -> Optional[JobErrorItem]:
    """从事件数据解析错误对象。"""
    if not isinstance(value, dict):
        return None

    code = value.get("code")
    message = value.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        return None

    context = value.get("context")
    if context is not None and not isinstance(context, dict):
        context = None
    return JobErrorItem(code=code, message=message, context=context)


def _has_error(errors: list[JobErrorItem], target: JobErrorItem) -> bool:
    """判断错误是否已存在，避免事件折叠重复写入。"""
    return any(
        error.code == target.code and error.message == target.message
        for error in errors
    )
