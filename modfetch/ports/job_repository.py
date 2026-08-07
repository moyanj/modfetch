"""作业存储端口"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from modfetch.domain.events import BuildEvent


@dataclass
class JobRecord:
    """作业记录（创建时写入）"""

    id: str
    config_dict: Dict[str, Any]
    status: str = "pending"  # pending | running | completed | failed
    phase: str = "idle"  # idle | resolve | download | package


@dataclass
class JobSnapshot:
    """作业状态快照（页面刷新恢复用）"""

    id: str
    status: str
    phase: str
    stats: Dict[str, int] = field(default_factory=dict)
    results: Optional[List[Dict[str, Any]]] = None
    errors: Optional[List[Dict[str, Any]]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobRepository(Protocol):
    """作业持久化接口"""

    async def create(self, job: JobRecord) -> None:
        ...

    async def get(self, job_id: str) -> Optional[JobRecord]:
        ...

    async def append_event(self, event: BuildEvent) -> None:
        """追加事件（实现侧负责状态折叠与历史回放）"""
        ...

    async def update_snapshot(self, snapshot: JobSnapshot) -> None:
        ...
