"""向后兼容 shim — 作业管理已迁入 modfetch.adapters.jobs"""

from modfetch.adapters.jobs.state import (  # noqa: F401
    JobErrorItem,
    JobResultItem,
    JobState,
    JobStats,
)
from modfetch.adapters.jobs.manager import (  # noqa: F401
    JobApplicationService,
    JobManager,
)

__all__ = [
    "JobState",
    "JobStats",
    "JobResultItem",
    "JobErrorItem",
    "JobApplicationService",
    "JobManager",
]
