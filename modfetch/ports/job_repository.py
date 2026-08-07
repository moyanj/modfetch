"""作业存储端口"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from modfetch.domain.events import BuildEvent


@dataclass
class JobRecord:
    """作业记录（创建时写入）"""

    id: str  #: 作业 ID
    config_dict: Dict[str, Any]  #: 原始配置字典
    status: str = "pending"  #: 状态：pending | running | completed | failed
    phase: str = "idle"  #: 阶段：idle | resolve | download | package


@dataclass
class JobSnapshot:
    """作业状态快照（页面刷新恢复用）"""

    id: str  #: 作业 ID
    status: str  #: 状态
    phase: str  #: 阶段
    stats: Dict[str, int] = field(default_factory=dict)  #: 统计（下载数/字节等）
    results: Optional[List[Dict[str, Any]]] = None  #: 输出结果列表
    errors: Optional[List[Dict[str, Any]]] = None  #: 错误列表
    started_at: Optional[str] = None  #: 开始时间（ISO8601）
    completed_at: Optional[str] = None  #: 完成时间（ISO8601）


class JobRepository(Protocol):
    """作业持久化接口

    契约约定：实现负责作业的创建、查询与事件折叠，供 Web 层恢复状态。
    """

    async def create(self, job: JobRecord) -> None:
        """持久化一条新作业记录

        实现期望：写入 job 的初始状态；重复 ID 的行为由实现决定（覆盖或报错）
        """
        ...

    async def get(self, job_id: str) -> Optional[JobRecord]:
        """按 ID 读取作业记录

        实现期望：存在返回 JobRecord，不存在返回 None
        """
        ...

    async def append_event(self, event: BuildEvent) -> None:
        """追加事件（实现侧负责状态折叠与历史回放）

        实现期望：
            - 依据 event 更新作业的 status/phase/stats 等折叠状态
            - 保留事件历史以支持订阅回放；失败不得抛出（记录日志即可）
        """
        ...

    async def update_snapshot(self, snapshot: JobSnapshot) -> None:
        """写入作业状态快照

        实现期望：以 snapshot 覆盖该作业的当前快照，供页面刷新恢复
        """
        ...
