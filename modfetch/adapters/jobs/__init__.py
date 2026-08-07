"""作业适配器"""

from modfetch.adapters.jobs.state import (
    JobErrorItem,
    JobResultItem,
    JobState,
    JobStats,
)
from modfetch.adapters.jobs.manager import JobApplicationService, JobManager

__all__ = [
    "JobState",
    "JobStats",
    "JobResultItem",
    "JobErrorItem",
    "JobApplicationService",
    "JobManager",
]
