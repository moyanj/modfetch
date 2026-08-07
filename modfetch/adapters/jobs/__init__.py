"""作业适配器

Web 作业管理的内存实现：
- JobState/JobStats/JobResultItem/JobErrorItem: 作业状态与事件折叠模型
- JobApplicationService: 创建/启动/查询/订阅的作业应用服务
"""

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
